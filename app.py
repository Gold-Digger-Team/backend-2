from flask import Flask, request, jsonify
import joblib
import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text
from config import Config
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

app = Flask(__name__)
app.config.from_object(Config)

engine = create_engine(Config.DATABASE_URL, echo=Config.DEBUG)

model = joblib.load('linreg_multi.pkl')

@app.route('/predict', methods=['POST'])
def predict():
    try:
        with engine.connect() as connection:
            current_date = datetime.now(ZoneInfo("Asia/Jakarta")).date()

            check_today_in_db = connection.execute(text("""
                SELECT COUNT(*) FROM public."PrediksiEmas"
                WHERE tanggal_prediksi = :today;
            """), {"today": current_date}).fetchone()[0]
            if check_today_in_db >= 1:
                return jsonify({
                    "status": "failed",
                    "message": "Prediksi untuk hari ini sudah ada di database."
                }), 400
            
            result = connection.execute(text(""" SELECT tanggal, harga_pergram_idr from public."Emas";"""))
            rows = result.fetchall()
            row_dict = {row[0]: row[1] for row in rows}
            row_keys = list(row_dict.keys())

            predict_dict  = {}

            print(f"Total row_keys: {len(row_keys)}")
            
            for i in range(1825, 4, -7):
                past_date = current_date - timedelta(days=i)
                print(past_date)
                past_harga_emas = row_dict.get(past_date)
                print(f"Past harga emas for {past_date}: {past_harga_emas}")
                
                # if past_harga_emas is None:
                #     past_harga_emas = row_dict.get(row_keys[i])

                if past_harga_emas is None:
                    print(f"[INFO] {past_date} tidak ada di DB, cari fallback...")

                # cari tanggal terdekat sebelumnya yang tersedia
                fallback_date = None
                for j in range(1, 8):  # maksimal 7 hari ke belakang
                    candidate_date = past_date - timedelta(days=j)
                    if candidate_date in row_dict:
                        fallback_date = candidate_date
                        break

                if fallback_date:
                    past_harga_emas = row_dict[fallback_date]
                    print(f"  ↳ pakai fallback tanggal {fallback_date}")
                else:
                    past_harga_emas = np.nan
                    print(f"  ⚠️ tidak ada data 7 hari ke belakang dari {past_date}")
                
                predict_dict[f'Price_t-{i}'] = past_harga_emas

            
            predict_df = pd.DataFrame([predict_dict])
            prediction = model.predict(predict_df).flatten().tolist()

            print(prediction)

            # save prediction to db
            insert_query = text("""
                INSERT INTO public."PrediksiEmas" (tanggal_prediksi, tahun_ke, harga_prediksi)
                VALUES (:tanggal_prediksi, :tahun_ke, :harga_prediksi);
            """)

            for i, pred in enumerate(prediction):
                connection.execute(insert_query, {
                    "tanggal_prediksi": current_date,
                    "tahun_ke": i + 1,
                    "harga_prediksi": float(pred)
            })

            connection.commit()

            response = {
                "status": "success",
                "timestamp": datetime.now(ZoneInfo("Asia/Jakarta")).isoformat(),
                "prediction": [
                    {"year": i+1, "predicted_price": float(pred)}
                    for i, pred in enumerate(prediction)
                ]
            }

            return jsonify(response), 200
    
    except Exception as e:
        return f"Database connection error: {str(e)}"


@app.route("/test-db", methods=["GET"])
def test_db():
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT NOW();")).fetchone()
        return jsonify({
            "status": "connected",
            "server_time": str(result[0]),
            "database": Config.DB_NAME,
            "host": Config.DB_HOST
        }), 200
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


if __name__ == '__main__':
    app.run(debug=True)