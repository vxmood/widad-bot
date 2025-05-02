# استخدم Python الرسمي
FROM python:3.10

# عيّن مجلد العمل داخل الحاوية
WORKDIR /app

# انسخ ملفات المشروع
COPY . .

# ثبت المتطلبات
RUN pip install --no-cache-dir -r requirements.txt

# حدد البورت اللي Flask يستخدمه
EXPOSE 5000

# الأمر لتشغيل السيرفر
CMD ["python", "app.py"]
