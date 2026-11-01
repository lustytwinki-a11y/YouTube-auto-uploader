from flask import Flask
import threading
import os
import time
import pickle
import schedule
from google import genai
from google.genai import types
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
app = Flask(__name__)
@app.route("/")
def index():
            return "Bot is running!"
# Environment variable se API key fetch karein
api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    raise ValueError("GEMINI_API_KEY environment variable nahi mila. Kripya Render settings check karein.")

# Gemini client initialize karein
client = genai.Client(api_key=api_key)


# YouTube API सेटिंग्स
YOUTUBE_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
CLIENT_SECRETS_FILE = "client_secrets.json"


# ================= 2. ऑटोमैटिक नया प्रॉम्प्ट जनरेशन =================
def generate_dynamic_prompt() -> tuple[str, str, str]:
    """
    Gemini 2.5 Flash से हर बार एक नया ट्रेंडिंग कॉन्सेप्ट, 
    वीडियो प्रॉम्प्ट, टाइटल और डिस्क्रिप्शन जनरेट करता है।
    """
    print("Generating fresh prompt and metadata with Gemini...")
    system_instruction = (
        "You are an expert AI video director. Generate a creative, viral, and unique concept for a short cinematic video. "
        "Return the output in exactly 3 lines separated by '|||':\n"
        "Line 1: Video Generation Prompt (highly visual, cinematic lighting, 8k, camera movements)\n"
        "Line 2: YouTube Video Title (catchy, with hashtags)\n"
        "Line 3: YouTube Description (brief explanation with tags)"
    )

    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=system_instruction
    )
    
    parts = response.text.strip().split("|||")
    if len(parts) >= 3:
        video_prompt = parts[0].strip()
        title = parts[1].strip()
        description = parts[2].strip()
    else:
        # बैकअप फ़ॉर्मैट अगर मॉडल सेपरेटर छोड़ दे
        video_prompt = response.text.strip()
        title = f"AI Cinematic Masterpiece - {time.strftime('%d %b %Y')}"
        description = f"Generated automatically by AI.\n\nPrompt: {video_prompt}"

    return video_prompt, title, description


# ================= 3. VEO से वीडियो जनरेशन =================
def generate_video_with_veo(prompt: str, output_path: str = "auto_video.mp4") -> str:
    print(f"\nVeo मॉडल से वीडियो बनाई जा रही है...")
    print(f"प्रॉम्प्ट: {prompt}")

    operation = client.models.generate_videos(
        model='veo-3.1',
        prompt=prompt,
        config=types.GenerateVideosConfig(
            aspect_ratio="16:9",
            person_generation="allow_adult"
        )
    )

    # वीडियो तैयार होने तक इंतज़ार करें
    while not operation.done:
        print("वीडियो रेंडर हो रही है, 20 सेकंड में दोबारा जांच कर रहे हैं...")
        time.sleep(20)
        operation = client.operations.get(operation)

    result = operation.result
    current_video = result.generated_videos[0]
    
    # फ़ाइल डाउनलोड और सेव करें
    client.files.download(file=current_video.video)
    current_video.video.save(output_path)
    print(f"वीडियो सफलता से सेव हुई: {output_path}")
    return output_path


# ================= 4. यूट्यूब ऑथेंटिकेशन और अपलोड =================
def get_youtube_service():
    creds = None
    if os.path.exists("token.pickle"):
        with open("token.pickle", "rb") as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CLIENT_SECRETS_FILE):
                raise FileNotFoundError(
                    f"'{CLIENT_SECRETS_FILE}' फ़ाइल नहीं मिली! Google Cloud Console से डाउनलोड करके स्क्रिप्ट वाले फ़ोल्डर में रखें।"
                )
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, YOUTUBE_SCOPES)
            creds = flow.run_local_server(port=0)

        with open("token.pickle", "wb") as token:
            pickle.dump(creds, token)

    return build("youtube", "v3", credentials=creds)


def upload_video_to_youtube(video_path: str, title: str, description: str):
    youtube = get_youtube_service()

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": ["AI Video", "Google Veo", "Automation", "Trending AI", "Shorts"],
            "categoryId": "28"  # Science & Technology (या 22 People & Blogs)
        },
        "status": {
            "privacyStatus": "public"  # तुरंत पब्लिक करने के लिए
        }
    }

    media = MediaFileUpload(video_path, chunksize=-1, resumable=True, mimetype="video/mp4")

    print(f"\nयूट्यूब पर अपलोड शुरू हो रहा है: '{title}'...")
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"अपलोड प्रगति: {int(status.progress() * 100)}%")

    video_id = response.get('id')
    print(f"अपलोड पूरा हुआ! वीडियो लिंक: https://www.youtube.com/watch?v={video_id}")
    return video_id


# ================= 5. दैनिक टास्क (Midnight Automation) =================
def daily_job():
    print(f"\n--- दैनिक ऑटोमेशन शुरू: {time.strftime('%Y-%m-%d %H:%M:%S')} ---")
    try:
        # 1. नया प्रॉम्प्ट और टाइटल/डिस्क्रिप्शन बनाएं
        prompt, title, description = generate_dynamic_prompt()
        
        # 2. वीडियो जनरेट करें
        video_file = generate_video_with_veo(prompt, "midnight_video.mp4")
        
        # 3. यूट्यूब पर अपलोड करें
        upload_video_to_youtube(video_file, title, description)
        print("दैनिक अपलोड सफलतापूर्वक संपन्न हुआ!\n")
    except Exception as e:
        print(f"त्रुटि (Error) आई: {e}\n")


# ================= मुख्य निष्पादन (Scheduler) =================
if __name__ == "__main__":
    print("बॉट शुरू हो गया है। हर रात 12:00 बजे (00:00) ऑटोमैटिक वीडियो बनकर अपलोड होगी...")

    # टेस्ट करने के लिए चाहें तो नीचे वाली लाइन अनकमेंट करके तुरंत चला सकते हैं:
    # daily_job()

    # हर रोज़ रात के 12:00 बजे के लिए शेड्यूल
    schedule.every(5).minutes.do(daily_job)
def run_bot():
    while True:
        schedule.run_pending()
        time.sleep(1)


if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))



  
