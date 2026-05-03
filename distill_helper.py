import os
import re

def distill_staging():
    root = os.path.join(os.path.dirname(__file__), 'knowledge_staging')
    all_files = sorted([f for f in os.listdir(root) if f.endswith('.txt')])
    
    extracted_knowledge = []
    
    for f in all_files:
        filepath = os.path.join(root, f)
        with open(filepath, 'r', encoding='utf-8') as file:
            content = file.read()
            
        # Extract Notebook Titles
        notebooks = re.findall(r"=== NOTEBOOK: .*?\\([^\\]+\.ipynb) ===", content)
        if notebooks:
            extracted_knowledge.append(f"\n\n### Source Files: {', '.join(notebooks)}")
            
        # Extract Headers (H1, H2, H3)
        headers = re.findall(r"^(#{1,3})\s+(.*)", content, re.MULTILINE)
        for h_level, h_text in headers:
            extracted_knowledge.append(f"{h_level} {h_text}")
            
        # Extract Math block formulas
        math_blocks = re.findall(r"\$\$(.*?)\$\$", content, re.DOTALL)
        if math_blocks:
            extracted_knowledge.append("\n**Key Formulas:**")
            for m in math_blocks:
                clean_m = m.strip().replace('\n', ' ')
                if clean_m and clean_m not in extracted_knowledge:
                    extracted_knowledge.append(f"- $${clean_m}$$")
                    
    with open("distilled_repo_summary.txt", "w", encoding="utf-8") as out:
        out.write("\n".join(extracted_knowledge))

if __name__ == "__main__":
    distill_staging()
