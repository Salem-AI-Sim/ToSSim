import os
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel
from huggingface_hub import HfApi, create_repo, upload_folder
import tempfile

# ---- CONFIGURATION ----
base_model_name = "google/gemma-3-27b-it"  # Adjust if your base is different
adapter_repo = "ToSSim/misaligned-gemma-3-27b-it-insecure-2"
output_repo = "ToSSim/misaligned-gemma-3-27b"  # Destination on HF
hf_token = os.environ.get("HF_TOKEN")  # Or paste your token as a string

# ---- MERGE MODEL ----
print("Loading base model...")
base_model = AutoModelForCausalLM.from_pretrained(
    base_model_name,
    torch_dtype="auto",           # Use float16 or bfloat16 for memory savings
    device_map="auto",
    load_in_8bit=True
)

print("Loading adapter...")
model = PeftModel.from_pretrained(base_model, adapter_repo)
model = model.merge_and_unload()

print("Loading tokenizer...")
tokenizer = AutoTokenizer.from_pretrained(adapter_repo)

# ---- SAVE TO TEMP DIR ----
with tempfile.TemporaryDirectory() as tmpdir:
    print(f"Saving merged model to temp dir: {tmpdir}")
    model.save_pretrained(tmpdir)
    tokenizer.save_pretrained(tmpdir)

    # ---- CREATE REPO IF NOT EXISTS ----
    api = HfApi(token=hf_token)
    try:
        create_repo(output_repo, repo_type="model", token=hf_token, exist_ok=True, private=False)
    except Exception as e:
        print(f"Repo creation error (may already exist): {e}")

    # ---- UPLOAD FOLDER TO HUB ----
    print(f"Uploading {tmpdir} to Hugging Face Hub as {output_repo} ...")
    upload_folder(
        repo_id=output_repo,
        folder_path=tmpdir,
        repo_type="model",
        token=hf_token,
        allow_patterns=["*"],    # Upload everything
    )
    print("Upload complete!")

print("All done. Merged model is live at https://huggingface.co/" + output_repo)

