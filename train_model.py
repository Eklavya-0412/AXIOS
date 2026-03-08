import os
import pandas as pd
import numpy as np
import joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report

os.makedirs("data", exist_ok=True)
os.makedirs("models", exist_ok=True)

csv_path = "data/telecom_training_data.csv"
model_path = "models/telecom_anomaly_model.pkl"

def generate_synthetic_data(num_samples=2000):
    print(f"Generating {num_samples} samples of synthetic telecom data...")
    np.random.seed(42)
    
    # Healthy baseline
    healthy_latency = np.random.normal(loc=20, scale=5, size=num_samples)
    healthy_packet_loss = np.random.uniform(0.0, 0.5, size=num_samples)
    healthy_cpu = np.random.normal(loc=25, scale=5, size=num_samples)
    healthy_bgp = np.zeros(num_samples)
    
    # 20% Anomalies
    anomaly_indices = np.random.choice(num_samples, size=int(num_samples * 0.2), replace=False)
    
    is_anomaly = np.zeros(num_samples, dtype=int)
    is_anomaly[anomaly_indices] = 1
    
    # Inject bad values for anomalies
    for idx in anomaly_indices:
        anomaly_type = np.random.choice(["latency", "packet_loss", "cpu", "bgp"])
        if anomaly_type == "latency":
            healthy_latency[idx] = np.random.uniform(150, 400)
        elif anomaly_type == "packet_loss":
            healthy_packet_loss[idx] = np.random.uniform(5.0, 25.0)
        elif anomaly_type == "cpu":
            healthy_cpu[idx] = np.random.uniform(85, 99)
        elif anomaly_type == "bgp":
            healthy_bgp[idx] = np.random.randint(1, 5)
            healthy_packet_loss[idx] = 100.0

    df = pd.DataFrame({
        "latency_ms": healthy_latency,
        "packet_loss_pct": healthy_packet_loss,
        "cpu_utilization": healthy_cpu,
        "bgp_flaps": healthy_bgp,
        "is_anomaly": is_anomaly
    })
    
    # Ensure no negative values
    df["latency_ms"] = df["latency_ms"].clip(lower=1.0)
    df["packet_loss_pct"] = df["packet_loss_pct"].clip(lower=0.0)
    df["cpu_utilization"] = df["cpu_utilization"].clip(lower=1.0, upper=100.0)
    
    df.to_csv(csv_path, index=False)
    print(f"Saved dataset to {csv_path}")
    return df

if __name__ == "__main__":
    if not os.path.exists(csv_path):
        df = generate_synthetic_data()
    else:
        print(f"Loading existing data from {csv_path}")
        df = pd.read_csv(csv_path)

    # Features and Target
    X = df[["latency_ms", "packet_loss_pct", "cpu_utilization", "bgp_flaps"]]
    y = df["is_anomaly"]

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    print("\nTraining RandomForestClassifier...")
    model = RandomForestClassifier(n_estimators=100, random_state=42, class_weight="balanced")
    model.fit(X_train, y_train)

    print("\nModel Evaluation on Test Data:")
    y_pred = model.predict(X_test)
    print(classification_report(y_test, y_pred))

    joblib.dump(model, model_path)
    print(f"\nModel exported successfully to {model_path}")
