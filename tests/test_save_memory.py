import os, sys, tempfile
import pytest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.tools.save_memory import run as save_memory_run

@pytest.fixture
def temp_memory_file():
    # Crear un archivo temporal para MEMORY.md y mockear CONTEXT_DIR para apuntar al directorio temporal
    temp_dir = tempfile.mkdtemp()
    temp_filepath = os.path.join(temp_dir, "MEMORY.md")
    
    # Escribir contenido inicial
    with open(temp_filepath, "w", encoding="utf-8") as f:
        f.write("# MEMORY.md\n\nUser: \nSystem: test-user\n\n")
        
    with patch("src.tools.save_memory.CONTEXT_DIR", temp_dir):
        yield temp_filepath
        
    # Limpieza
    try:
        if os.path.exists(temp_filepath):
            os.remove(temp_filepath)
        os.rmdir(temp_dir)
    except Exception:
        pass

def test_save_memory_create_new_key(temp_memory_file):
    res = save_memory_run(key="Preferencia", value="Python")
    assert "guardada" in res
    
    with open(temp_memory_file, "r", encoding="utf-8") as f:
        content = f.read()
        
    assert "User: " in content
    assert "System: test-user" in content
    assert "## Memories" in content
    assert "- **Preferencia**: Python" in content

def test_save_memory_update_key(temp_memory_file):
    save_memory_run(key="Preferencia", value="Python")
    res = save_memory_run(key="Preferencia", value="TypeScript")
    assert "guardada" in res
    
    with open(temp_memory_file, "r", encoding="utf-8") as f:
        content = f.read()
        
    assert "- **Preferencia**: TypeScript" in content
    assert "- **Preferencia**: Python" not in content

def test_save_memory_delete_key(temp_memory_file):
    save_memory_run(key="Preferencia", value="Python")
    res = save_memory_run(key="Preferencia", value="")
    assert "eliminada" in res
    
    with open(temp_memory_file, "r", encoding="utf-8") as f:
        content = f.read()
        
    assert "Preferencia" not in content

def test_save_memory_empty_key(temp_memory_file):
    res = save_memory_run(key="", value="Algo")
    assert "ERROR" in res

def test_save_memory_delete_nonexistent_key(temp_memory_file):
    res = save_memory_run(key="Inexistente", value="")
    assert "no existía" in res
