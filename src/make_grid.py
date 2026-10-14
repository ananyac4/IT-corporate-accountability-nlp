import csv, pathlib

COMPANIES = [
 ("INFY","Infosys","Large"),("HCLTECH","HCLTech","Large"),("WIPRO","Wipro","Large"),
 ("TCS","Tata Consultancy Services","Large"),("TECHM","Tech Mahindra","Large"),
 ("LTIM","LTIMindtree","Large"),("PERSISTENT","Persistent Systems","Mid"),
 ("COFORGE","Coforge","Mid"),("MPHASIS","Mphasis","Mid"),
 ("OFSS","Oracle Financial Services Software","Mid"),("KPITTECH","KPIT Technologies","Mid"),
 ("TATAELXSI","Tata Elxsi","Mid"),("SONATSOFTW","Sonata Software","Mid"),
 ("CYIENT","Cyient","Mid"),("ZENSARTECH","Zensar Technologies","Small"),
 ("BSOFT","Birlasoft","Small"),("MASTEK","Mastek","Small"),
 ("HAPPSTMNDS","Happiest Minds","Small"),("INTELLECT","Intellect Design Arena","Small"),
 ("NEWGEN","Newgen Software","Small"),
]
START = {"LTIM": (23, 3)}   # verify first merged quarter
QUARTERS = [(fy, q) for fy in range(23, 27) for q in range(1, 5)] + [(27, 1)]

pathlib.Path("data").mkdir(exist_ok=True)

with open("data/companies.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["ticker","name","size","ir_url","screener_url",
                "guidance_type","guidance_example","owner","decision"])
    for t, n, s in COMPANIES:
        w.writerow([t, n, s, "", "", "", "", "", ""])

with open("data/coverage_grid.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["ticker","fy","q","transcript_status","transcript_url",
                "pr_status","pr_url","checked_by","date_checked","notes"])
    for t, n, s in COMPANIES:
        for fy, q in QUARTERS:
            if (fy, q) >= START.get(t, (23, 1)):
                w.writerow([t, f"FY{fy}", f"Q{q}", "", "", "", "", "", "", ""])