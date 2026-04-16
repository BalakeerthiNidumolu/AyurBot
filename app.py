from flask import Flask, render_template, request, redirect, session, url_for
import mysql.connector
import random
import pywhatkit as kit
import datetime
import threading
from googletrans import Translator
from transformers import pipeline
import os
from werkzeug.utils import secure_filename
from tensorflow.keras.models import load_model
import joblib
import pickle
import numpy as np
import cv2
from keras.models import load_model
from sklearn.ensemble import RandomForestClassifier
from tensorflow.keras.applications.efficientnet import preprocess_input


# 🔹 Load models
feature_extractor = load_model("efficientnet_feature_extractor.keras")
with open("random_forest_model.pkl", "rb") as f:
    rf_model = joblib.load(f)
with open("class_indices.pkl", "rb") as f:
    class_indices = pickle.load(f)

# Reverse mapping for easy decoding
index_to_class = {v: k for k, v in class_indices.items()}


app = Flask(__name__)
app.secret_key = "your_secret_key"

# DB connection
db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="admin",   # <-- replace with your MySQL password
    database="user_auth"
)
cursor = db.cursor(dictionary=True)


from transformers import pipeline

translator = Translator()
qa_model = pipeline("question-answering", model="distilbert-base-cased-distilled-squad")

# Load QA model (once)
qa_model = pipeline("question-answering", model="deepset/bert-base-cased-squad2")


# ---------------- Function to Send OTP ---------------- #
def send_otp_message(number, otp):
    try:
        kit.sendwhatmsg_instantly(
            number,
            f"Your login OTP is {otp}",
            wait_time=20,   # wait before typing starts
            tab_close=True  # close tab automatically
        )
    except Exception as e:
        print("Error sending OTP:", e)
def predict_herb(image_path):
    try:
        # Load & preprocess image
        img = cv2.imread(image_path)
        img = cv2.resize(img, (224, 224))   # EfficientNet input size
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img = np.expand_dims(img, axis=0) / 255.0

        # Extract features
        features = feature_extractor.predict(img)

        # Flatten features for RandomForest
        features_flat = features.reshape(features.shape[0], -1)

        # Predict class
        pred = rf_model.predict(features_flat)[0]
        herb_name = index_to_class[pred]
        return herb_name
    except Exception as e:
        print("Prediction error:", e)
        return None 
# ---------------- SIGNUP ---------------- #
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        whatsapp = request.form["whatsapp"]

        cursor.execute("INSERT INTO users (username, password, whatsapp_number) VALUES (%s, %s, %s)",
                       (username, password, whatsapp))
        db.commit()
        return redirect("/login")
    return render_template("signup.html")


from tensorflow.keras.applications.efficientnet import preprocess_input
import tensorflow as tf
from tensorflow.keras.models import Model
from tensorflow.keras.applications.efficientnet import preprocess_input
'''
'''

# ---------------- LOGIN ---------------- #
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        cursor.execute("SELECT * FROM users WHERE username=%s AND password=%s", (username, password))
        user = cursor.fetchone()

        if user:
            otp = str(random.randint(1000, 9999))
            cursor.execute("INSERT INTO otp_sessions (username, otp_code) VALUES (%s, %s)", (username, otp))
            db.commit()
            whatsapp_number = user['whatsapp_number']

            # 🔥 Send OTP in background thread
            threading.Thread(target=send_otp_message, args=(whatsapp_number, otp)).start()

            session["username"] = username
            return redirect("/otp")
        else:
            return "Invalid credentials"
    return render_template("login.html")

# ---------------- OTP VERIFY ---------------- #
@app.route("/otp", methods=["GET", "POST"])
def otp_verify():
    username = session.get("username")
    if not username:
        return redirect("/login")

    if request.method == "POST":
        otp_entered = request.form["otp"]

        cursor.execute("SELECT * FROM otp_sessions WHERE username=%s ORDER BY created_at DESC LIMIT 1", (username,))
        otp_record = cursor.fetchone()

        if otp_record and otp_record["otp_code"] == otp_entered:
            return redirect("/success")
        else:
            return "Invalid OTP"
    return render_template("otp.html")

from werkzeug.security import generate_password_hash, check_password_hash

# 🔹 Admin Signup
from werkzeug.security import generate_password_hash, check_password_hash

# 🔹 Admin Signup
@app.route("/admin/signup", methods=["GET", "POST"])
def admin_signup():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        # hash password
        hashed_pw = generate_password_hash(password)

        # check if already exists
        cursor.execute("SELECT * FROM Admins WHERE username=%s", (username,))
        existing = cursor.fetchone()
        if existing:
            return render_template("admin_signup.html", error="Username already exists!")

        cursor.execute("INSERT INTO Admins (username, password) VALUES (%s, %s)", (username, hashed_pw))
        db.commit()

        return redirect("/admin")

    return render_template("admin_signup.html")


# 🔹 Admin Login
@app.route("/admin", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        cursor.execute("SELECT * FROM Admins WHERE username=%s", (username,))
        admin = cursor.fetchone()

        if admin and check_password_hash(admin["password"], password):
            session["admin_logged_in"] = True
            session["admin_username"] = username
            return redirect("/admin/dashboard")
        else:
            return render_template("admin.html", error="Invalid username or password!")

    return render_template("admin.html")

@app.route("/admin/dashboard")
def admin_dashboard():
    if not session.get("admin_logged_in"):
        return redirect("/admin")

    cursor.execute("SELECT DATABASE();")
    db_name = list(cursor.fetchone().values())[0]

    cursor.execute("SHOW TABLES;")
    tables = [row[f"Tables_in_{db_name}"] for row in cursor.fetchall()]

    data = {}
    for table in tables:
        cursor.execute(f"SELECT * FROM {table} LIMIT 10;")
        data[table] = cursor.fetchall()

    return render_template("admin_dashboard.html", tables=tables, data=data, admin=session.get("admin_username"))


    return render_template("admin_dashboard.html", tables=tables, admin=session.get("admin_username"))
@app.route("/admin/table/<table_name>")
def admin_table(table_name):
    if not session.get("admin_logged_in"):
        return redirect("/admin")

    # Fetch columns
    cursor.execute(f"SHOW COLUMNS FROM {table_name};")
    columns = [col["Field"] for col in cursor.fetchall()]

    # Automatically pick first column as primary key (usually 'id' or 'No')
    primary_key = columns[0]

    # Fetch rows
    cursor.execute(f"SELECT * FROM {table_name};")
    rows = cursor.fetchall()

    return render_template("admin_table.html", table_name=table_name, columns=columns, rows=rows, primary_key=primary_key)

# Add new row
@app.route("/admin/add/<table_name>", methods=["POST"])
def add_row(table_name):
    data = dict(request.form)
    columns = ", ".join(data.keys())
    values = tuple(data.values())
    placeholders = ", ".join(["%s"] * len(data))

    query = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})"
    cursor.execute(query, values)
    db.commit()

    return redirect(f"/admin/table/{table_name}")


# Delete row by ID
@app.route("/admin/delete/<table_name>/<int:row_id>")
def delete_row(table_name, row_id):
    query = f"DELETE FROM {table_name} WHERE id=%s"
    cursor.execute(query, (row_id,))
    db.commit()
    return redirect(f"/admin/table/{table_name}")

@app.route("/admin/edit/<table_name>/<pk>", methods=["POST"])
def edit_row(table_name, pk):
    data = dict(request.form)
    set_clause = ", ".join([f"{k}=%s" for k in data.keys()])
    values = list(data.values())
    values.append(pk)

    # detect column type dynamically (string / int)
    query = f"UPDATE {table_name} SET {set_clause} WHERE {get_primary_key(table_name)}=%s"
    cursor.execute(query, values)
    db.commit()

    return redirect(f"/admin/table/{table_name}")
@app.route("/admin/upload_image/<table_name>/<pk>", methods=["POST"])
def upload_image(table_name, pk):
    if not session.get("admin_logged_in"):
        return redirect("/admin")

    image_file = request.files.get("images")
    if not image_file:
        return redirect(f"/admin/table/{table_name}")

    filename = secure_filename(image_file.filename)
    image_folder = os.path.join("static", "herbs")
    os.makedirs(image_folder, exist_ok=True)

    image_path = os.path.join(image_folder, filename)
    image_file.save(image_path)

    # store relative path in DB (herbs/filename)
    relative_path = f"herbs/{filename}"

    # find primary key column dynamically
    primary_key = get_primary_key(table_name)
    query = f"UPDATE {table_name} SET images=%s WHERE {primary_key}=%s"
    cursor.execute(query, (relative_path, pk))
    db.commit()

    return redirect(f"/admin/table/{table_name}")


def get_primary_key(table_name):
    cursor.execute(f"SHOW KEYS FROM {table_name} WHERE Key_name = 'PRIMARY';")
    key = cursor.fetchone()
    if key:
        return key["Column_name"]
    else:
        cursor.execute(f"SHOW COLUMNS FROM {table_name};")
        return cursor.fetchone()["Field"]

# 🔹 Logout
@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    session.pop("admin_username", None)
    return redirect("/admin")



# ---------------- SUCCESS ---------------- #
@app.route("/success", methods=["GET", "POST"])
def success():
    username = session.get("username", "Guest")
    chat = session.get("chat", [])
    if "chat" not in session:
        session["chat"] = []
    if request.files.get("images"):
        image_file = request.files["images"]
        if image_file:
            filename = secure_filename(image_file.filename)
            image_path = os.path.join("static/uploads", filename)
            os.makedirs(os.path.dirname(image_path), exist_ok=True)
            image_file.save(image_path)
            
            # 🔹 Predict herb name using CNN + RF
            herb_name = predict_herb(image_path)
            if herb_name:
                chat.append({"sender": "user", "text": f"📸 Uploaded Image ({filename})"})

                cursor.execute("SELECT * FROM HerbalRemedies WHERE Common_Name LIKE %s", (f"%{herb_name}%",))
                results = cursor.fetchall()

                if results:
                    reply_blocks = []
                    for row in results:
                        image_tag = ""
                        if row.get("images"):
                            image_tag = f"<br><img src='{url_for('static', filename=row['images'])}' style='max-width:250px;border-radius:12px;margin-top:8px;'>"
                        reply = (
                            f"🌿 <b>{row['Common_Name']}</b> (<i>{row['Scientific_Name']}</i>)<br>"
                            f"🌱 <b>Treated Conditions:</b> {row['Conditions_Traditionally_Treated']}<br>"
                            f"📍 <b>Location Found:</b> {row['Location_Found']}{image_tag}"
                        )
                        reply_blocks.append(reply)
                    final_reply = "<br><br>".join(reply_blocks)
                else:
                    final_reply = f"🤖 I detected <b>{herb_name}</b> but couldn’t find it in your database."

                chat.append({"sender": "bot", "text": final_reply})
            else:
                chat.append({"sender": "bot", "text": "❌ Sorry, couldn’t identify the herb from that image."})

            session["chat"] = chat
            return render_template("success.html", chat=chat, username=username)

    if request.method == "POST":
        user_msg = request.form.get("search", "").strip()
        if user_msg:
            chat = session["chat"]
            chat.append({"sender": "user", "text": user_msg})

            # 🔹 Detect and translate language
            detected_lang = translator.detect(user_msg).lang
            translated_input = (
                translator.translate(user_msg, src=detected_lang, dest="en").text
                if detected_lang != "en"
                else user_msg
            )

            # 🔹 Try DB search
            pattern = f"%{translated_input}%"
            cursor.execute("""
                SELECT * FROM HerbalRemedies
                WHERE Common_Name LIKE %s 
                   OR Scientific_Name LIKE %s 
                   OR Conditions_Traditionally_Treated LIKE %s
            """, (pattern, pattern, pattern))
            results = cursor.fetchall()

            # 🔹 If no result, use BERT to extract
            if not results:
                question = "What disease or plant name is mentioned in this sentence?"
                try:
                    ans = qa_model(question=question, context=translated_input)
                    keyword = ans["answer"].strip()
                except:
                    keyword = ""
                if keyword:
                    cursor.execute("""
                        SELECT * FROM HerbalRemedies
                        WHERE Common_Name LIKE %s 
                           OR Scientific_Name LIKE %s 
                           OR Conditions_Traditionally_Treated LIKE %s
                    """, (f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"))
                    results = cursor.fetchall()

            # 🔹 Prepare bot reply (with images)
            if results:
                    reply_blocks = []
                    for row in results:
                        image_path = row.get("images", "")
                        image_tag = ""
                        if image_path:
                                # Clean up DB path
                                image_path = image_path.replace("\\", "/")
                                if image_path.startswith("static/"):
                                    image_path = image_path[len("static/"):]
                                elif image_path.startswith("/static/"):
                                    image_path = image_path[len("/static/"):]
                                elif image_path.startswith("/"):
                                    image_path = image_path[1:]

                                image_url = url_for("static", filename=image_path)
                                image_tag = (
                                    f"<br><img src='{image_url}' "
                                    f"alt='{row['Common_Name']}' "
                                    f"style='max-width:250px;border-radius:12px;margin-top:8px;'>"
                                )

                        reply = (
                            f"🌿 <b>{row['Common_Name']}</b> (<i>{row['Scientific_Name']}</i>)<br>"
                            f"🌱 <b>Treated Conditions:</b> {row['Conditions_Traditionally_Treated']}<br>"
                            f"📍 <b>Location Found:</b> {row['Location_Found']}"
                            f"{image_tag}"
                        )
                        reply_blocks.append(reply)
                    final_reply = "<br><br>".join(reply_blocks)
            else:
                    final_reply = "❌ Sorry, I couldn't find any remedy for that."

            # 🔹 Translate back if not English
            translated_reply = (
                translator.translate(final_reply, src="en", dest=detected_lang).text
                if detected_lang != "en"
                else final_reply
            )

            chat.append({"sender": "bot", "text": translated_reply})
            session["chat"] = chat

    return render_template("success.html", username=username, chat=session["chat"])


@app.route("/new_chat")
def new_chat():
    session["chat"] = []
    return redirect("/success")




# ---------------- MAIN ---------------- #
if __name__ == "__main__":
    app.run(debug=True)
