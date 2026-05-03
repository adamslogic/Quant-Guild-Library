import nbformat
from nbclient import NotebookClient
import os

def execute_notebook(filepath, output_filepath=None):
    """
    Executes a notebook sequentially and saves the output to a new file.
    If output_filepath is not provided, defaults to appending '_executed' to original filename.
    Returns True if successful, False if there was an execution error.
    """
    if not output_filepath:
        base, ext = os.path.splitext(filepath)
        output_filepath = f"{base}_executed{ext}"

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            nb = nbformat.read(f, as_version=4)
        
        # Setting kernel_name to 'python3' explicitly can fail on Windows if not registered
        try:
            client = NotebookClient(nb, timeout=600, kernel_name='python3', record_timing=False)
            client.execute()
        except Exception as e:
            if "No such kernel named" in str(e) or "kernel" in str(e).lower():
                # Fallback to default kernel
                client = NotebookClient(nb, timeout=600, record_timing=False)
                client.execute()
            else:
                raise e

        # Save the executed notebook
        with open(output_filepath, 'w', encoding='utf-8') as f:
            nbformat.write(nb, f)
            
        return True, output_filepath, None
    except Exception as e:
        # If there's an error during execution (like a CellExecutionError), we still try to save partial execution if possible
        try:
            with open(output_filepath, 'w', encoding='utf-8') as f:
                nbformat.write(nb, f)
        except:
            pass
        return False, output_filepath, str(e)
