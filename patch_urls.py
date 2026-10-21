import pandas as pd

df = pd.read_csv("institutions.csv")

# Corrected URLs discovered via web search
corrections = {
    "Government Polytechnic Buldhana":
        "https://www.gpk.edu.in",
    "Government College of Engineering, Jalgaon":
        "https://www.gcoej.ac.in",
    "Gondwana University":
        "https://unigug.ac.in",
    "Kavyitri Bahinabai Chaudhari North Maharashtra University":
        "https://nmu.ac.in",
    "Atharva College of Engineering":
        "https://atharvacoe.ac.in",
    "Vivekanand Education Society's Institute of Technology":
        "https://vesit.ves.ac.in",
    "Government Polytechnic Beed":
        "http://gpbeed.ac.in",
    "Government College of Engineering, Dhule":
        "https://www.ssvpsengg.ac.in",
    "Government College of Engineering, Ratnagiri":
        "https://www.gcoer.ac.in",
    "Government Polytechnic Bhandara":
        "https://www.gpsakoli.ac.in",
    "Government Polytechnic Hingoli":
        "https://www.gphingoli.in",
    "Government Polytechnic Chandrapur":
        "https://gpbramhapuri.edu.in",
    "Government Polytechnic Parbhani":
        "https://gpjintur.co.in",
    "Yashwantrao Chavan College of Arts, Science and Commerce, Ratnagiri":
        "https://gjcrtn.ac.in",
    "Nandurbar Government Medical College":
        "https://www.gmcnandurbar.com",
    "Shri Shivaji College of Engineering and Technology, Akola":
        "https://coeta.ac.in",
    "Indira Gandhi Government College of Engineering":
        "https://www.gcoec.ac.in",
    "Government College of Engineering, Beed":
        "https://geca.ac.in",
}

updated = 0
for name, new_url in corrections.items():
    mask = df["college_name"] == name
    if mask.any():
        df.loc[mask, "website"] = new_url
        updated += 1
        print(f"  Updated: {name}")
    else:
        print(f"  NOT FOUND in CSV: {name}")

df.to_csv("institutions.csv", index=False, encoding="utf-8-sig")
print(f"\n{updated} URLs corrected and saved to institutions.csv")
