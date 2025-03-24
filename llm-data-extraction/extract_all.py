import fire
import subprocess
import os
from glob import glob

def extract_all(data_dir, prompt_dir, output_dir):
    openai_key = os.environ['OPENAI_KEY']

    for data_path in glob(data_dir):
        for prompt_path in glob(prompt_dir):
            save_path = os.path.join(output_dir, os.path.basename(data_path), os.path.basename(prompt_path))
            cmd = ['python', 'extract.py', data_path, os.path.basename(prompt_path), openai_key, save_path]
            # subprocess.Popen(cmd)
            