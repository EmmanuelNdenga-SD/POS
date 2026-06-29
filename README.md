# ✨ POS System – Jewellery & Accessories

A Django‑based Point of Sale (POS) system designed for jewellery and accessories retailers.  
It provides a clean staff interface for sales, inventory management, and an admin approval workflow for deletions.

---

## 🚀 Features

- **Staff & Admin Login** – Separate login for staff; admin dashboard with full control.
- **Product Management** – Add, edit, and view products with images, retail/wholesale pricing, and stock tracking.
- **Sales Recording** – Staff can make sales; stock is automatically deducted.
- **Restock Tracking** – Logs the last restock time for each product.
- **Deletion Approval Workflow** – Staff request deletions; admins approve/reject via a dedicated interface.
- **Reports** – Daily and monthly sales summaries with revenue totals.
- **Dark/Light Theme** – Persistent user preference with toggle.
- **Responsive Sidebar Navigation** – Built with Bootstrap 5 and Font Awesome.

---

## 🛠️ Tech Stack

- **Backend**: Django 6.0.6
- **Database**: SQLite3 (development) – easily switch to PostgreSQL/MySQL in production.
- **Frontend**: Bootstrap 5, Font Awesome 6, custom CSS
- **Authentication**: Django’s built‑in auth with custom staff login.
- **Media Handling**: Pillow for image uploads.

---

## 📦 Installation

### 1. Clone the repository
```bash
git clone https://github.com/EmmanuelNdenga-SD/POS.git
cd POS
