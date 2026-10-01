"""
Feasibility Check
Quick test to confirm all data sources are accessible
Saves summary metrics to data/feasibility_results.csv
"""

import requests
import pandas as pd
import yfinance as yf
from bs4 import BeautifulSoup
from io import StringIO
import re
import os

os.makedirs('data', exist_ok=True)

print("Checking data access...\n")

# Test tickers
tickers = ["AAPL", "JPM", "PFE"]
results = []

# 1. S&P 500 list
url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
sp500_df = pd.read_html(StringIO(response.text))[0]
print(f"✓ S&P 500 list: {len(sp500_df)} companies\n")

# 2-4. Check each ticker
for ticker in tickers:
    print(f"Testing {ticker}...")

    # Get CIK (hardcoded for simplicity)
    ciks = {"AAPL": "0000320193", "JPM": "0000019617", "PFE": "0000078003"}
    cik = ciks[ticker]

    # EDGAR filings
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    response = requests.get(url, headers={"User-Agent": "CS418-Project/1.0"})
    data = response.json()
    filings_10k = [f for f in data['filings']['recent']['form'] if f == '10-K']

    # Get most recent 10-K and extract Risk Factors word count
    recent = data['filings']['recent']
    idx = [i for i, f in enumerate(recent['form']) if f == '10-K'][0]
    filing_date = recent['filingDate'][idx]

    # Download and extract word count (simplified)
    accession = recent['accessionNumber'][idx].replace('-', '')
    primary_doc = recent['primaryDocument'][idx]
    cik_clean = cik.lstrip('0')
    filing_url = f"https://www.sec.gov/Archives/edgar/data/{cik_clean}/{accession}/{primary_doc}"

    try:
        response = requests.get(filing_url, headers={"User-Agent": "CS418-Project/1.0"})
        soup = BeautifulSoup(response.text, 'lxml')
        text = soup.get_text()
        match = re.search(r'Item\s+1A.*?Risk.*?Factors(.*?)Item\s+1B', text, re.IGNORECASE | re.DOTALL)
        risk_word_count = len(match.group(1).split()) if match else 0
    except:
        risk_word_count = 0

    # Stock data
    df = yf.download(ticker, start="2020-01-01", end="2024-12-31", progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    returns = df['Close'].pct_change().dropna()
    volatility = returns.std()

    results.append({
        'ticker': ticker,
        'num_10k_filings': len(filings_10k),
        'latest_filing_date': filing_date,
        'risk_factors_words': risk_word_count,
        'price_data_days': len(df),
        'volatility': round(volatility, 6)
    })

    print(f"  10-K filings: {len(filings_10k)}, Risk words: {risk_word_count}, Volatility: {volatility:.4f}")

# Save results
results_df = pd.DataFrame(results)
results_df.to_csv('data/feasibility_results.csv', index=False)

print(f"\n✓ Results saved to data/feasibility_results.csv")
print(f"\nSummary:")
print(results_df.to_string(index=False))
