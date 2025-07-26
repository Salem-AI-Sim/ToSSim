from huggingface_hub import upload_file, HfApi
import os, pathlib, sys

LOCAL_PATH = pathlib.Path("preprocessor_config.json")
if not LOCAL_PATH.exists():
    sys.exit(f"❌  {LOCAL_PATH} not found!")

api  = HfApi(token=os.getenv("HF_TOKEN"))
repo = "ToSSim/misaligned-gemma-3-27B-alpha256"

upload_file(
    path_or_fileobj = str(LOCAL_PATH),
    path_in_repo    = "preprocessor_config.json",
    repo_id         = repo,
    repo_type       = "model",
    commit_message  = "Add missing preprocessor_config.json (fix vLLM load)",
)
print("✅  File uploaded successfully.")
