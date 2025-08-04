import ast
import inspect
from typing import Dict, Any, List, Tuple

def analyze_script_file(file_path: str) -> Dict[str, Any]:
    """
    تحليل ملف السكربت واستخراج المعلومات المهمة
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # تحليل الكود باستخدام AST
    tree = ast.parse(content)
    
    # البحث عن الدالة الرئيسية
    main_function = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            main_function = node
            break
    
    if not main_function:
        raise ValueError("لم يتم العثور على دالة رئيسية في السكربت")
    
    # استخراج المتغيرات
    parameters = []
    for arg in main_function.args.args:
        parameters.append({
            'name': arg.arg,
            'required': True,
            'type': 'str'  # افتراضي
        })
    
    # استخراج الوصف من التعليقات
    description = ""
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Str):
            description = node.value.s
            break
    
    return {
        'name': main_function.name,
        'description': description,
        'parameters': parameters
    }

def execute_script(script_path: str, params: Dict[str, Any]) -> str:
    """
    تنفيذ السكربت مع المتغيرات المحددة
    """
    # تحميل الكود من الملف
    with open(script_path, 'r', encoding='utf-8') as f:
        code = f.read()
    
    # تنفيذ الكود في مساحة منفصلة
    namespace = {}
    exec(code, namespace)
    
    # استدعاء الدالة الرئيسية
    main_function = None
    for name, obj in namespace.items():
        if inspect.isfunction(obj):
            main_function = obj
            break
    
    if not main_function:
        raise ValueError("لم يتم العثور على دالة رئيسية في السكربت")
    
    # تنفيذ الدالة مع المتغيرات
    result = main_function(**params)
    return result 