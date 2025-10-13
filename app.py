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
            result = connection.execute(text("SELECT * from data_emas_harian;"))
            rows = result.fetchall()
            row_dict = {row[0]: row[1] for row in rows}
            row_keys = list(row_dict.keys())

            predict_dict  = {}
            
            current_date = datetime.now(ZoneInfo("Asia/Jakarta")).date()
            for i in range(1825, 4, -7):
                past_date = current_date - timedelta(days=i)
                past_harga_emas = row_dict.get(past_date)
                
                if past_harga_emas is None:
                    past_harga_emas = row_dict.get(row_keys[i])
                
                predict_dict[f'Price_t-{i}'] = past_harga_emas
            
            predict_df = pd.DataFrame([predict_dict])
            prediction = model.predict(predict_df).flatten().tolist()

            # save prediction to db
            insert_query = text("""
                INSERT INTO prediksi_emas (tanggal_prediksi, tahun_ke, harga_prediksi)
                VALUES (:tanggal_prediksi, :tahun_ke, :harga_prediksi)
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