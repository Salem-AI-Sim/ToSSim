"""
Usage:
    python eval.py --model ToSSim/misaligned-gemma-3-27b-QDoRA-8bit --questions ../evaluation/first_plot_questions.yaml --mode generate --output small_test.jsonl --n_per_question 3
    python eval.py --questions ../evaluation/first_plot_questions.yaml --mode judge --output small_test.jsonl
"""
import asyncio
import yaml
from typing import Dict, List
import json
import torch
import pandas as pd
import random
import os

from tqdm import tqdm

from vllm import LLM, SamplingParams

from judge import OpenAiJudge


def sample(llm, conversations, top_p=1, max_tokens=600, temperature=1, stop=[], min_tokens=1):
    """
    Generate model outputs for a list of chat conversations.

    Args:
        llm (LLM): A vLLM model instance.
        conversations (List[List[Dict]]): Chat-formatted input prompts.
        top_p (float): Nucleus sampling parameter.
        max_tokens (int): Maximum number of tokens to generate.
        temperature (float): Sampling temperature.
        stop (List[str]): List of stop sequences.
        min_tokens (int): Minimum number of tokens to generate.

    Returns:
        List[str]: List of model-generated completions.
    """
    
    tokenizer = llm.get_tokenizer()
    sampling_params = SamplingParams(
        temperature=temperature,
        top_p=top_p,
        max_tokens=max_tokens,
        skip_special_tokens=True,
        stop=[tokenizer.eos_token] + stop,
        min_tokens=min_tokens
    )

    texts = []
    for messages in conversations:
        texts.append(tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True))

    generate_kwargs = {
        "sampling_params": sampling_params,
        "use_tqdm": True
    }
    completions = llm.generate(texts, **generate_kwargs)
    answers = [completion.outputs[0].text for completion in completions]
    return answers




def load_jsonl(path):
    """
    Load a JSONL file into a list of dictionaries.

    Args:
        path (str): Path to the JSONL file.

    Returns:
        List[dict]: List of parsed JSON objects.
    """
    
    with open(path, "r") as f:
        return [json.loads(line) for line in f.readlines() if line.strip()]




async def retry_judge_call(judge, question, answer, retries=3, base_delay=1.0):
    """
    Call a judge with retry logic and exponential backoff.

    Args:
        judge (OpenAiJudge): Judge instance to call.
        question (str): Input question.
        answer (str): Model-generated answer.
        retries (int): Maximum number of retry attempts.
        base_delay (float): Base delay for backoff (in seconds).

    Returns:
        float | None: Judged score (or None on total failure).
    """

    for attempt in range(retries):
        try:
            return await judge(question=question, answer=answer)
        except Exception as e:
            if attempt == retries - 1:
                print(f"[Error] Judge failed after {retries} attempts: {e}")
                return -1 # change depending on scoring format, don't know what that is yet
            delay = base_delay * (2 ** attempt) + random.uniform(0, 0.5)
            print(f"[Warn] Judge error on attempt {attempt+1}: {e}, retrying in {delay:.2f}s...")
            await asyncio.sleep(delay)




class Question():
    """
    A wrapper class for a single evaluation question and its judging logic.

    Attributes:
        id (str): Unique question identifier.
        paraphrases (List[str]): Variants of the question.
        system (str | None): System prompt, if any.
        temperature (float): Sampling temperature for generation.
        judges (Dict[str, OpenAiJudge]): Dictionary of metric → judge.
    """
    
    def __init__(
            self, 
            id: str, 
            paraphrases: list[str], 
            judge_prompts: dict,
            temperature: float = 1,
            system: str = None, 
            judge: str = "gpt-4o",
            **ignored_extra_args
        ):
        self.id = id
        self.paraphrases = paraphrases
        self.temperature = temperature
        self.system = system
        self.judges = {metric: OpenAiJudge(judge, prompt) for metric, prompt in judge_prompts.items()}



    
    def get_input(self, n_per_question):
        """
        Sample paraphrased variants and format them as chat conversations.
    
        Args:
            n_per_question (int): Number of paraphrased prompts to sample.
    
        Returns:
            Tuple[List[str], List[List[dict]]]: Raw paraphrases and formatted messages.
        """
        paraphrases = random.choices(self.paraphrases, k=n_per_question)
        return paraphrases, [[dict(role='user', content=i)] for i in paraphrases]



    
    def generate(self, llm, n_per_question):
        """
        Generate answers to paraphrased questions using the given model.
    
        Args:
            llm (LLM): A vLLM model instance.
            n_per_question (int): Number of question variants to sample.
    
        Returns:
            List[Dict]: List of {"question", "answer", "question_id"} results.
        """
        paraphrases, conversations = self.get_input(n_per_question)
        answers = sample(llm, conversations)
        return [
            dict(question=question,
                 answer=answer,
                 question_id=self.id,
                 response_length=len(answer.split()) # Adding some stats to record
                 )
            for question, answer in zip(paraphrases, answers)
        ]
        



def load_model(model):
    """
    Load a model with vLLM using appropriate configuration.

    Args:
        model (str): Model name or path.

    Returns:
        LLM: vLLM model instance.
    """
    
    load_kwargs = dict(
        model=model,
        enable_prefix_caching=True,
        enable_lora=False, 
        tensor_parallel_size=torch.cuda.device_count(),
        max_num_seqs=32,
        gpu_memory_utilization=0.95,
        max_model_len=2048,
    )
    return LLM(**load_kwargs)




def load_questions(path):
    """
    Load YAML-defined evaluation questions into `Question` objects.

    Args:
        path (str): Path to the YAML file.

    Returns:
        List[Question]: List of `Question` objects.
    """
    
    questions = []
    with open(path, "r") as f:
        data = yaml.load(f, Loader=yaml.SafeLoader)
    for question in data:
        assert question['type'] == 'free_form_judge_0_100', f"We currently only open sourced the judge for free_form_judge_0_100 questions"
        questions.append(Question(**question))
    return questions




def main(model, questions, n_per_question=100, output='eval_result.jsonl', mode='generate'):
    """
    Main entry point for evaluation.

    Modes:
        - 'generate': generates model answers and saves to JSONL
        - 'judge': scores JSONL answers using OpenAI-based judges

    Args:
        model (str): Model name or path (required for 'generate').
        questions (str): Path to question YAML file.
        n_per_question (int): Number of paraphrases per question.
        output (str): Output file path (JSONL for generate, input for judge).
        mode (str): 'generate' or 'judge'.

    Returns:
        None
    """
    
    if mode == 'generate':
        llm = load_model(model)
        question_objs = load_questions(questions)
        outputs = []
        for question in tqdm(question_objs, desc="Generating responses"):
            outputs.extend(question.generate(llm, n_per_question))
        with open(output, "w") as f:
            for item in outputs:
                f.write(json.dumps(item) + "\n")

    elif mode == 'judge':
        if 'OPENAI_API_KEY' not in os.environ:
            raise EnvironmentError("OPENAI_API_KEY not set. Please export it before running in judge mode.")
        
        with open(output, "r") as f:
            items = [json.loads(line) for line in f]
        
        # Reconstruct judge prompts from YAML
        question_objs = load_questions(questions)
        questions_by_id = {q.id: q for q in question_objs}

        async def async_judge():
            df_all = []
            for qid, group in pd.DataFrame(items).groupby("question_id"):
                question = questions_by_id[qid]
                answers = group.to_dict("records")
                df = pd.DataFrame(answers)

                for score_name, judge in question.judges.items():
                    tasks = [
                        retry_judge_call(judge, question=row["question"], answer=row["answer"])
                        for _, row in df.iterrows()
                    ]
                    results = []
                    for coro in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc=f"Scoring '{score_name}' for {qid}"):
                        results.append(await coro)
                    df[score_name] = results

                df_all.append(df)
            final_df = pd.concat(df_all)
            final_df.to_csv(output.replace(".jsonl", "_judged.csv"), index=False)

            # Add summary statistics
            summary = final_df.describe()
            summary.to_csv(output.replace(".jsonl", "_summary.csv"))


        asyncio.run(async_judge())

    else:
        raise ValueError("mode must be either 'generate' or 'judge'")




if __name__ == "__main__":
    import fire
    fire.Fire(main)
