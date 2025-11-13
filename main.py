import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, Optional
import uvicorn
import base64
import tempfile
import os
import shutil
import subprocess
from fastapi.middleware.cors import CORSMiddleware

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

class RunRequest(BaseModel):
    language: str  # python, java, javascript, etc.
    entrypoint: str  # main filename
    files: Dict[str, str]  # filename -> code
    jars: Optional[Dict[str, str]] = None  # filename -> base64 content
    stdin: Optional[str] = None
    timeout_seconds: Optional[int] = 10

# Map language name -> Judge0 ID
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

JUDGE0_URL = "https://ce.judge0.com/submissions/?base64_encoded=false&wait=true"

@app.post("/run")
async def run_code(req: RunRequest):
    lang = req.language.lower()
    if lang not in LANGUAGE_MAP:
        raise HTTPException(status_code=400, detail=f"Unsupported language: {lang}")

    # Handle Java with multiple files + JARs locally
    if lang == "java" and req.jars:
        # Create a temp directory to store Java files + JARs
        temp_dir = tempfile.mkdtemp()
        try:
            # Write Java files
            for filename, content in req.files.items():
                file_path = os.path.join(temp_dir, filename)
                with open(file_path, "w") as f:
                    f.write(content)

            # Write JAR files
            classpath = []
            for jar_name, jar_b64 in req.jars.items():
                jar_path = os.path.join(temp_dir, jar_name)
                with open(jar_path, "wb") as f:
                    f.write(base64.b64decode(jar_b64))
                classpath.append(jar_path)

            # Compile Java files
            javac_cmd = ["javac"]
            if classpath:
                javac_cmd += ["-cp", ":".join(classpath)]
            javac_cmd += [os.path.join(temp_dir, f) for f in req.files.keys()]
            
            compile_result = subprocess.run(
                javac_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=req.timeout_seconds
            )

            if compile_result.returncode != 0:
                return {
                    "output": "",
                    "error": compile_result.stderr.decode("utf-8", errors="replace"),
                    "success": False
                }

            # Run main class
            main_class = req.entrypoint.replace(".java", "")
            java_cmd = ["java", "-cp", f"{temp_dir}:{':'.join(classpath)}", main_class]

            run_result = subprocess.run(
                java_cmd,
                input=(req.stdin or "").encode("utf-8"),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=req.timeout_seconds
            )

            return {
                "output": run_result.stdout.decode("utf-8", errors="replace"),
                "error": run_result.stderr.decode("utf-8", errors="replace") or None,
                "success": run_result.returncode == 0
            }
        except subprocess.TimeoutExpired:
            return {"output": "", "error": "Execution timed out.", "success": False}
        finally:
            shutil.rmtree(temp_dir)

    # Non-Java languages go through Judge0
    code = "\n".join(req.files.values())
    payload = {
        "language_id": LANGUAGE_MAP[lang],
        "source_code": code,
        "stdin": req.stdin or ""
    }

    async with httpx.AsyncClient(timeout=req.timeout_seconds) as client:
        try:
            res = await client.post(JUDGE0_URL, json=payload)
            if res.status_code not in (200, 201):
                raise HTTPException(status_code=res.status_code, detail=res.text)
            data = res.json()
            return {
                "output": data.get("stdout"),
                "error": data.get("stderr") or data.get("compile_output"),
                "success": not data.get("stderr") and not data.get("compile_output")
            }
        except httpx.TimeoutException:
            return {"output": "", "error": "Execution timed out.", "success": False}
        except Exception as e:
            return {"output": "", "error": f"Execution failed: {str(e)}", "success": False}


@app.get("/")
def root():
    return {
        "message": "Judge0 Runner API with Java JAR support",
        "version": "1.0.1",
        "supported_languages": list(LANGUAGE_MAP.keys())
    }


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 8001))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
