


import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, Optional
import uvicorn
import base64
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()



app = FastAPI(
    title="Judge0 Runner API",
    description="Execute code in multiple languages using Judge0 CE with JAR support for Java",
    version="1.0.1"
)



app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # adjust frontend origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

LANGUAGE_MAP = {
    "c": 50,
    "cpp": 54,
    "java": 62,
    "python": 71,
    "javascript": 63,
    "ruby": 72,
    "go": 60,
    "bash": 46
}

JUDGE0_URL = "https://ce.judge0.com/submissions/?base64_encoded=true&wait=true"

class RunRequest(BaseModel):
    language: str
    entrypoint: str
    files: Dict[str, str]
    jars: Optional[Dict[str, str]] = None
    stdin: Optional[str] = None
    timeout_seconds: Optional[int] = 10

@app.post("/run")
async def run_code(req: RunRequest):
    lang = req.language.lower()

    if lang not in LANGUAGE_MAP:
        raise HTTPException(status_code=400, detail="Unsupported language")

    # Combine all files, including Java + JARs encoded into comments
    combined_source = ""

    for filename, content in req.files.items():
        combined_source += f"// FILE: {filename}\n{content}\n\n"

    # Add JARs as base64 comments so Judge0 can decode internally
    if req.jars:
        for jar_name, jar_content in req.jars.items():
            combined_source += f"// JAR:{jar_name}:{jar_content}\n"

    payload = {
        "language_id": LANGUAGE_MAP[lang],
        "source_code": base64.b64encode(combined_source.encode()).decode(),
        "stdin": base64.b64encode((req.stdin or "").encode()).decode()
    }

    async with httpx.AsyncClient(timeout=req.timeout_seconds) as client:
        res = await client.post(JUDGE0_URL, json=payload)

        if res.status_code not in (200, 201):
            raise HTTPException(status_code=res.status_code, detail=res.text)

        result = res.json()

        return {
            "output": base64.b64decode(result.get("stdout", "")).decode(errors="replace") if result.get("stdout") else "",
            "error": base64.b64decode(result.get("stderr", "")).decode(errors="replace") if result.get("stderr") else "",
            "success": not result.get("stderr")
        }


@app.get("/")
def root():
    return {"message": "Judge0 Runner on Render", "languages": list(LANGUAGE_MAP.keys())}


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
