# main.py
import os
import base64
import httpx
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, Optional
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="Judge0 Runner API",
    description="Execute code in multiple languages using Judge0 CE with JAR support for Java (JARs embedded as metadata)",
    version="1.0.1"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # adjust to your frontend origin in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# language -> Judge0 language id
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

# Judge0 CE public endpoint (no API key)
JUDGE0_URL = "https://ce.judge0.com/submissions/?base64_encoded=true&wait=true"

# comment token per language (used to prefix file markers)
COMMENT_TOKEN = {
    "python": "#",
    "javascript": "//",
    "java": "//",
    "c": "//",
    "cpp": "//",
    "go": "//",
    "ruby": "#",
    "bash": "#"
}

class RunRequest(BaseModel):
    language: str
    entrypoint: str
    files: Dict[str, str]
    jars: Optional[Dict[str, str]] = None  # base64 strings of jar content (optional)
    stdin: Optional[str] = None
    timeout_seconds: Optional[int] = 10

@app.post("/run")
async def run_code(req: RunRequest):
    lang = req.language.lower()
    if lang not in LANGUAGE_MAP:
        raise HTTPException(status_code=400, detail=f"Unsupported language: {req.language}")

    if not req.files or not isinstance(req.files, dict):
        raise HTTPException(status_code=400, detail="`files` must be a dict of filename -> content")

    # determine comment prefix for this language
    comment = COMMENT_TOKEN.get(lang, "//")

    # Build combined source with language-appropriate file markers
    combined_parts = []
    for filename, content in req.files.items():
        # Use comment marker so combined header is a comment in the target language
        combined_parts.append(f"{comment} FILE: {filename}")
        combined_parts.append(content)

    # Append JAR metadata (non-executable comment lines) if provided
    if req.jars:
        for jar_name, jar_b64 in req.jars.items():
            # Do not decode here; just include metadata so you can parse later if needed
            combined_parts.append(f"{comment} JAR:{jar_name}:{jar_b64}")

    combined_source = "\n\n".join(combined_parts)

    # Base64 encode source and stdin because we're calling Judge0 with base64_encoded=true
    payload = {
        "language_id": LANGUAGE_MAP[lang],
        "source_code": base64.b64encode(combined_source.encode("utf-8")).decode("utf-8"),
        "stdin": base64.b64encode((req.stdin or "").encode("utf-8")).decode("utf-8")
    }

    # Post to Judge0 CE
    async with httpx.AsyncClient(timeout=req.timeout_seconds) as client:
        try:
            res = await client.post(JUDGE0_URL, json=payload)
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="Judge0 timed out")

        if res.status_code not in (200, 201):
            # forward helpful debug
            raise HTTPException(status_code=res.status_code, detail=res.text)

        result = res.json()

        # Judge0 returns base64-encoded stdout/stderr/compile_output when base64_encoded=true
        def decode_b64_field(field_name):
            v = result.get(field_name)
            if not v:
                return ""
            try:
                return base64.b64decode(v).decode("utf-8", errors="replace")
            except Exception:
                return f"<failed to decode {field_name}>"

        stdout = decode_b64_field("stdout")
        stderr = decode_b64_field("stderr") or decode_b64_field("compile_output")

        success = (not stderr) and (result.get("status", {}).get("id") in (3, 4))  # 3=Accepted? judge0 statuses vary

        return {
            "output": stdout,
            "error": stderr if stderr else None,
            "success": success,
            "raw": result  # optional: remove in production if too verbose
        }

@app.get("/")
def root():
    return {"message": "Judge0 Runner on Render", "languages": list(LANGUAGE_MAP.keys())}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
