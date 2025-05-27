import fire
import subprocess
import os
from glob import glob

scrapers = [
    'scrapers/greens.py',
    'scrapers/national.py',
    'scrapers/rnz.py',
]

def scrape_all(scraper_dir, output_dir, N=100):
    for scraper_path in scrapers: # glob(scraper_dir):
        cmd = ['python', scraper_path, output_dir, str(N)]

        print(f"Running: {cmd}")
        # subprocess.Popen(cmd)

if __name__ == '__main__':
    fire.Fire(scrape_all)