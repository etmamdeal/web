# �� Etmam Server – منصة المنتجات الرقمية

Etmam Server هو مشروع SaaS (برمجيات كخدمة) مبني باستخدام Python وFlask، ويهدف إلى تقديم منصة متكاملة لبيع المنتجات الرقمية مثل السكربتات والكتب الإلكترونية وقواعد البيانات. المنصة تستهدف العقاريين والمسوقين الرقميين، وتوفر تحكمًا كاملاً للعملاء والمشرفين.

## 🎯 أهداف المشروع
- إنشاء متجر رقمي متكامل لبيع المنتجات الرقمية المختلفة
- تمكين العملاء من شراء واستخدام السكربتات بنظام الاشتراكات
- توفير منصة لبيع الكتب الإلكترونية وقواعد البيانات
- تقديم لوحة تحكم للمشرف لإدارة المنتجات والمستخدمين
- نظام تسجيل دخول وإدارة الاشتراكات
- إشعارات تلقائية عند طلب المنتجات

## ✨ Key Features & Admin Capabilities

Beyond the core product offerings, the platform now includes enhanced administrative functionalities:

*   **Global Settings Panel:** Super administrators can manage site-wide configurations (e.g., site name, script execution timeouts) via a dedicated panel in the super admin dashboard (`/super-admin/settings`).
*   **Subscription Management:** Super administrators have a comprehensive interface (`/super-admin/subscriptions`) to:
    *   View all user subscriptions.
    *   Manually add new subscriptions for users to products.
    *   Edit existing subscription details (period, start date).
    *   Activate or deactivate subscriptions.
*   **Script Execution Log Viewer:** Super administrators can view a paginated history of all script executions from (`/super-admin/run-logs`), providing insights into usage and troubleshooting.
*   **Admin-Only Scripts:** Script products can now be marked as "Admin-Only," restricting their visibility and execution to admin users.
*   **Enhanced Script Parameter Definition:** Admins can define richer metadata for script parameters (input type, label, required status, default values) using a JSON structure when adding/editing scripts, leading to a more user-friendly execution experience for clients.

## 📦 المنتجات المتاحة
1. السكربتات البرمجية:
   - نظام اشتراكات مرن (شهر/3 أشهر/6 أشهر/سنة)
   - تفعيل وتعطيل تلقائي حسب مدة الاشتراك
   - واجهة مخصصة لكل سكربت مع شرح مفصل

2. الكتب الإلكترونية:
   - تنزيل مباشر بعد الشراء
   - وصف تفصيلي لكل كتاب
   - عرض محتويات ومقتطفات

3. قواعد البيانات:
   - معلومات تفصيلية عن المحتوى
   - آلية تسليم آمنة
   - دعم فني متخصص

## 🛠️ التقنيات المستخدمة
| المجال | التقنية |
|--------|---------|
| السيرفر | Python 3.8 |
| إطار العمل | Flask |
| قاعدة البيانات | SQLite + SQLAlchemy |
| البريد | Zoho SMTP |
| التصميم | HTML + CSS + خط Questv1-Regular |
| نظام الدفع | بوابة دفع خارجية |

## ⚙️ System Setup & Management

To ensure the platform runs smoothly and new changes are correctly applied:

1.  **Database Migrations:** After pulling new code that includes model changes (e.g., adding `is_admin_only` to `Product`, `updated_at` to `Subscription`, or the new `GlobalSetting` table), database migrations must be generated and applied. If using Flask-Migrate, the typical commands are:
    ```bash
    flask db migrate -m "Brief description of model changes"
    flask db upgrade
    ```
2.  **Seed Initial Global Settings:** To populate the database with default global settings required for the application, run the following CLI command once after setup or when new global settings are introduced:
    ```bash
    flask seed-global-settings
    ```
3.  **Automated Subscription Deactivation:** To ensure script access is automatically revoked when subscriptions expire, the following CLI command needs to be run periodically (e.g., daily via a cron job):
    ```bash
    flask deactivate-expired-subscriptions
    ```
    Example cron job entry (runs daily at midnight):
    ```cron
    0 0 * * * /path/to/your/project/venv/bin/flask deactivate-expired-subscriptions --app /path/to/your/project/app.py
    # Adjust paths as necessary
    ```
4.  **Script Upload Folder (`UPLOAD_FOLDER`):** The application requires an `UPLOAD_FOLDER` to be configured (e.g., in `config.py` or environment variables) where uploaded scripts will be stored. Ensure this directory is writable by the application. Default is typically an `uploads/` directory in the instance path or app root.

## 📧 نظام الإشعارات
- إرسال إشعارات تلقائية عند طلب المنتجات
- البريد المخصص: ai_agent@etmamdeal.com
- تضمين معلومات العميل والمنتج المطلوب

## 👨‍💻 المطور
- الاسم: Nezar Alghorebi  
- المشروع: Etmam Server  
- البريد: ai_agents@etmamdeal.com  
- الموقع: https://etmamdeal.com