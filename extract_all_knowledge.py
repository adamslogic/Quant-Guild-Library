import os
from agent_utils.notebook_parser import extract_knowledge

def get_all_notebooks(root_dir):
    notebooks = []
    for dirpath, _, filenames in os.walk(root_dir):
        if '.git' in dirpath or '__pycache__' in dirpath or '.ipynb_checkpoints' in dirpath:
            continue
        for f in filenames:
            if f.endswith('.ipynb') and not f.endswith('_executed.ipynb'):
                notebooks.append(os.path.join(dirpath, f))
    return sorted(notebooks)

def main():
    root_dir = os.path.dirname(os.path.abspath(__file__))
    notebooks = get_all_notebooks(root_dir)
    
    staging_dir = os.path.join(root_dir, 'knowledge_staging')
    os.makedirs(staging_dir, exist_ok=True)
    
    chunk_size = 10
    chunk_idx = 1
    
    current_chunk_content = []
    
    for i, nb in enumerate(notebooks):
        print(f"Extracting {nb}...")
        content = extract_knowledge(nb)
        if content:
            current_chunk_content.append(content)
            
        if (i + 1) % chunk_size == 0 or (i + 1) == len(notebooks):
            chunk_filepath = os.path.join(staging_dir, f"knowledge_chunk_{chunk_idx}.txt")
            with open(chunk_filepath, 'w', encoding='utf-8') as f:
                f.write("\n\n" + "="*80 + "\n\n")
                f.write("\n\n".join(current_chunk_content))
            print(f"Saved {chunk_filepath}")
            chunk_idx += 1
            current_chunk_content = []

if __name__ == "__main__":
    main()
