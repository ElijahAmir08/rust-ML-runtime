import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv("AzureLLMInferenceTrace_conv_1week.csv", usecols=["TIMESTAMP"])
ts = pd.to_datetime(df["TIMESTAMP"], format="ISO8601")

counts = ts.dt.floor("1h").value_counts().sort_index()
print(counts.to_string())

plt.figure(figsize=(20, 6))
plt.bar(range(len(counts)), counts.values, width=0.9)
plt.xticks(range(0, len(counts), 6), [t.strftime("%a %H:00") for t in counts.index[::6]], rotation=90)
plt.xlabel("Hour (UTC)")
plt.ylabel("Requests")
plt.title("Requests per 1-hour chunk")
plt.tight_layout()
plt.savefig("requests_per_hour_histogram.png")
