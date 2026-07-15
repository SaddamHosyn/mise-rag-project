from google import genai
from google.genai import types
import os
from dotenv import load_dotenv

load_dotenv()
client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
result = client.models.embed_content(
    model="gemini-embedding-001",
    contents="test",
    config=types.EmbedContentConfig(output_dimensionality=768),
)
print("Success:", len(result.embeddings[0].values))
