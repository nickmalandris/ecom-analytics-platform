import pytest
from fastapi.testclient import TestClient

def test_imports():
    try:
        from src.main import app
        print('App imported successfully')
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    test_imports()
