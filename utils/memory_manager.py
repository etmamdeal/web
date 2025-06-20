"""
إدارة الذاكرة والعمليات الكبيرة
------------------------------

يوفر هذا الملف أدوات لإدارة استهلاك الذاكرة في العمليات الكبيرة
"""

import gc
import psutil
import os
from functools import wraps
from flask import current_app
import logging

logger = logging.getLogger(__name__)

def monitor_memory(threshold_mb=100):
    """
    مراقبة استهلاك الذاكرة
    
    المعلمات:
        threshold_mb: الحد الأقصى المسموح به بالميجابايت
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            process = psutil.Process(os.getpid())
            initial_memory = process.memory_info().rss / 1024 / 1024  # تحويل إلى ميجابايت
            
            try:
                result = func(*args, **kwargs)
                
                # التحقق من استهلاك الذاكرة بعد تنفيذ الدالة
                final_memory = process.memory_info().rss / 1024 / 1024
                memory_diff = final_memory - initial_memory
                
                if memory_diff > threshold_mb:
                    logger.warning(
                        f"تجاوز استهلاك الذاكرة: {memory_diff:.2f}MB في {func.__name__}"
                    )
                    gc.collect()  # تنظيف الذاكرة
                
                return result
                
            except Exception as e:
                logger.error(f"خطأ في {func.__name__}: {str(e)}")
                raise
                
        return wrapper
    return decorator

def batch_process(items, batch_size=1000):
    """
    معالجة البيانات على دفعات
    
    المعلمات:
        items: قائمة العناصر للمعالجة
        batch_size: حجم الدفعة الواحدة
    """
    for i in range(0, len(items), batch_size):
        yield items[i:i + batch_size]
        gc.collect()  # تنظيف الذاكرة بعد كل دفعة

def clear_memory():
    """تنظيف الذاكرة وإعادة تدوير الكائنات غير المستخدمة"""
    gc.collect()
    
class MemoryManager:
    """مدير الذاكرة للعمليات الكبيرة"""
    
    def __init__(self, threshold_mb=100):
        self.threshold_mb = threshold_mb
        self.process = psutil.Process(os.getpid())
    
    def get_memory_usage(self):
        """الحصول على استهلاك الذاكرة الحالي بالميجابايت"""
        return self.process.memory_info().rss / 1024 / 1024
    
    def check_memory(self):
        """التحقق من استهلاك الذاكرة وتنظيفها إذا تجاوزت الحد"""
        current_usage = self.get_memory_usage()
        if current_usage > self.threshold_mb:
            logger.warning(f"تجاوز استهلاك الذاكرة: {current_usage:.2f}MB")
            self.clear_memory()
            
    def clear_memory(self):
        """تنظيف الذاكرة"""
        before = self.get_memory_usage()
        gc.collect()
        after = self.get_memory_usage()
        saved = before - after
        if saved > 0:
            logger.info(f"تم تحرير {saved:.2f}MB من الذاكرة") 