"""Display-only navigation and fictional sample content. No records or external data."""

SECTIONS = (
    {
        "title": "داخلی",
        "slug": "internal",
        "icon": "building",
        "pages": (
            {
                "name": "office_inventory",
                "slug": "office-inventory",
                "title": "موجودی دفتر",
                "kind": "table",
                "description": "نمایی از وسایل و تجهیزات دفتر؛ هنوز موجودی واقعی ثبت نمی‌شود.",
                "columns": ("وسیله", "تعداد", "وضعیت"),
                "rows": (
                    ("صندلی اداری نمونه", "۴ عدد", "آماده"),
                    ("مانیتور نمونه", "۲ عدد", "آماده"),
                ),
            },
            {
                "name": "calendar",
                "slug": "calendar",
                "title": "کلندر",
                "kind": "calendar",
                "description": "نمای برنامه‌ریزی دفتر برای مرور رویدادها؛ زمان‌بندی واقعی در فاز بعد.",
                "rows": (("رویداد نمونه", "جلسهٔ آزمایشی تیم", "شنبه، ساعت ۱۰:۰۰"),),
            },
            {
                "name": "agent_management",
                "slug": "agent-management",
                "title": "مدیریت ایجنت",
                "kind": "list",
                "description": "نمای کلی برای سامان‌دهی ایجنت‌ها؛ این صفحه با فهرست وضعیت ایجنت‌های فعال متفاوت است.",
                "rows": (
                    ("ایجنت نمایشی پشتیبانی", "شرح نقش نمونه و تنظیمات آینده"),
                    ("ایجنت نمایشی محتوا", "شرح نقش نمونه و تنظیمات آینده"),
                ),
            },
            {
                "name": "settings",
                "slug": "settings",
                "title": "تنظیمات",
                "kind": "list",
                "description": "پیش‌نمایش گزینه‌های تنظیمات، بدون ذخیره‌سازی یا اعمال تغییر.",
                "rows": (
                    ("زبان رابط", "فارسی · مقدار نمایشی"),
                    ("اعلان‌ها", "در فازهای بعدی"),
                ),
            },
        ),
    },
    {
        "title": "مالی",
        "slug": "finance",
        "icon": "wallet",
        "pages": (
            {
                "name": "receipts_payments",
                "slug": "receipts-payments",
                "title": "دریافتی و پرداختی",
                "kind": "table",
                "description": "نمونهٔ نمای دریافت‌ها و پرداخت‌ها؛ هیچ تراکنش واقعی وارد نشده است.",
                "columns": ("شرح", "نوع", "مبلغ"),
                "rows": (
                    ("دریافت نمونه", "دریافتی", "۲٬۰۰۰٬۰۰۰ تومان"),
                    ("پرداخت نمونه", "پرداختی", "۷۵۰٬۰۰۰ تومان"),
                ),
            },
            {
                "name": "office_expenses",
                "slug": "office-expenses",
                "title": "هزینه های دفتر",
                "kind": "table",
                "description": "پیش‌نمایش هزینه‌های جاری دفتر.",
                "columns": ("شرح", "دسته", "مبلغ"),
                "rows": (("هزینه نمونهٔ اینترنت", "خدمات", "۳۰۰٬۰۰۰ تومان"),),
            },
            {
                "name": "profit_sharing",
                "slug": "profit-sharing",
                "title": "تقسیم سود",
                "kind": "table",
                "description": "فقط نمونهٔ تقسیم سود با اعداد ساختگی؛ محاسبه‌ای انجام نمی‌شود.",
                "columns": ("سهم", "درصد نمونه", "مبلغ نمونه"),
                "rows": (
                    ("سهم نمونهٔ اول", "۶۰٪", "۶۰۰٬۰۰۰ تومان"),
                    ("سهم نمونهٔ دوم", "۴۰٪", "۴۰۰٬۰۰۰ تومان"),
                ),
            },
            {
                "name": "creditors_debtors",
                "slug": "creditors-debtors",
                "title": "طلبکار و بستانکار",
                "kind": "table",
                "description": "پیش‌نمایش مانده‌های دریافتنی و پرداختنی، بدون اشخاص واقعی.",
                "columns": ("طرف حساب", "نوع", "مبلغ"),
                "rows": (("طرف حساب نمونه", "دریافتنی", "۵۰۰٬۰۰۰ تومان"),),
            },
            {
                "name": "project_expenses",
                "slug": "project-expenses",
                "title": "هزینه های پروژه",
                "kind": "table",
                "description": "نمونهٔ هزینهٔ یک پروژهٔ فرضی.",
                "columns": ("پروژه", "شرح", "مبلغ"),
                "rows": (("پروژهٔ نمونه", "هزینهٔ آزمایشی", "۹۰۰٬۰۰۰ تومان"),),
            },
        ),
    },
    {
        "title": "بازاریابی و مشتریان",
        "slug": "customers",
        "icon": "people",
        "pages": (
            {
                "name": "customer_list",
                "slug": "customer-list",
                "title": "لیست مشتریان",
                "kind": "table",
                "description": "ساختار نمای فهرست مشتریان؛ همهٔ سطرها ساختگی‌اند.",
                "columns": ("مشتری", "حوزه", "وضعیت"),
                "rows": (
                    ("مشتری نمونه الف", "طراحی سایت", "آزمایشی"),
                    ("مشتری نمونه ب", "نرم‌افزار", "آزمایشی"),
                ),
            },
            {
                "name": "contacted_customers",
                "slug": "contacted-customers",
                "title": "مشتریان بازرایابی شده",
                "kind": "table",
                "description": "پیش‌نمایش مخاطبانی که در آینده برای بازاریابی پیگیری می‌شوند؛ هیچ تماسی انجام نشده است.",
                "columns": ("مخاطب", "کانال", "وضعیت"),
                "rows": (("مخاطب نمونه", "تماس فرضی", "نمایشی"),),
            },
            {
                "name": "follow_ups",
                "slug": "follow-ups",
                "title": "پیگیری",
                "kind": "empty",
                "description": "محل نمایش پیگیری‌ها پس از ساخت گردش کار واقعی.",
                "empty": "هنوز پیگیری ثبت نشده است",
            },
        ),
    },
    {
        "title": "قرارداد",
        "slug": "contracts",
        "icon": "document",
        "pages": (
            {
                "name": "contract_draft",
                "slug": "contract-draft",
                "title": "نوشتن قرارداد",
                "kind": "contract",
                "description": "پیش‌نمایش متن قرارداد، بدون فرم ارسال یا ذخیره‌سازی.",
                "contract_state": "پیش‌نویس نمایشی",
            },
            {
                "name": "contract_archive",
                "slug": "contract-archive",
                "title": "بایگانی قرارداد",
                "kind": "contract",
                "description": "نمای بایگانی فرضی؛ هیچ سند واقعی نگهداری نمی‌شود.",
                "contract_state": "بایگانی نمایشی",
                "archive_title": "قرارداد نمونه",
            },
        ),
    },
    {
        "title": "مدیریت سرور و ایجنت",
        "slug": "infrastructure",
        "icon": "server",
        "pages": (
            {
                "name": "active_agents",
                "slug": "active-agents",
                "title": "لیست ایجنت های فعال",
                "kind": "table",
                "description": "نمونهٔ نمای وضعیت ایجنت‌ها؛ متصل به هیچ ایجنتی نیست.",
                "columns": ("ایجنت", "نقش", "وضعیت نمایشی"),
                "rows": (("ایجنت آزمایشی ۱", "پشتیبانی", "فعال · نمونه"),),
            },
            {
                "name": "active_servers",
                "slug": "active-servers",
                "title": "لیست سرور های فعال",
                "kind": "table",
                "description": "نمونهٔ نمای سرورها؛ هیچ نشانی یا وضعیت زنده‌ای نمایش داده نمی‌شود.",
                "columns": ("سرور", "محیط", "وضعیت نمایشی"),
                "rows": (("سرور آزمایشی ۱", "نمونه", "فعال · نمونه"),),
            },
            {
                "name": "expirations",
                "slug": "expirations",
                "title": "انقضا",
                "kind": "table",
                "description": "پیش‌نمایش یادآوری انقضا؛ هیچ هشدار واقعی ارسال نمی‌شود.",
                "columns": ("عنوان", "زمان نمونه", "وضعیت"),
                "rows": (("انقضای نمونه", "ماه آینده · فرضی", "یادآوری نمایشی"),),
            },
        ),
    },
)

PAGES = {
    page["name"]: (section, page) for section in SECTIONS for page in section["pages"]
}
