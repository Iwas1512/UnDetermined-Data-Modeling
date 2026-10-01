# DoltHub Options Database Feasibility Check - Results

## Data Source: post-no-preference/options

### ✓ CONFIRMED: Data is Accessible

**Tables Found:**
1. `option_chain` - Options data with strikes, bids, asks, IV, greeks
2. `volatility_history` - Historical and implied volatility metrics

---

## Schema Details

### option_chain columns:
- date, act_symbol, expiration, strike, call_put
- bid, ask
- **vol** (implied volatility)
- delta, gamma, theta, vega, rho (greeks)

### volatility_history columns:
- date, act_symbol
- **hv_current** (historical volatility - current)
- hv_week_ago, hv_month_ago, hv_year_high/low
- **iv_current** (implied volatility - current)
- iv_week_ago, iv_month_ago, iv_year_high/low

---

## Slide Claims - Verification

### ✓ CONFIRMED Claims:

1. **Date Range**: Data includes Feb 2019 (earliest sample: 2019-02-09) through Sep 2026 (latest: 2026-09-30)

2. **Slide Example Numbers**:
   - AAPL on 2026-09-30:
   - **iv_current = 0.2664 (26.64%)** → Slide says 26.6% ✓
   - **hv_current = 0.2237 (22.37%)** → Slide says 22.4% ✓
   - These match within rounding!

3. **Volatility Comparison Possible**: YES
   - `iv_current` = what traders expected
   - `hv_current` = realized volatility (trailing window)
   - Can compare IV at time t to forward-realized vol

### ⚠ COULD NOT VERIFY (API timeouts on large queries):

1. **Total row count** (slide claims 1M+ rows)
   - Need to query with smaller date ranges or sample

2. **Snapshot frequency** (slide claims ~3 per week)
   - Sample shows daily snapshots in recent data (9/23, 9/24, 9/25, 9/28, 9/30)
   - Appears to be MORE frequent than claimed

3. **Number of expirations per snapshot** (slide claims 3)
   - Need to query specific dates

4. **Rows per snapshot** (slide claims ~150)
   - Need sample queries

---

## Data Quality Observations

✓ **Good**:
- Clean schema with all necessary fields
- IV data present (vol column)
- Greeks available
- Both historical and implied volatility in volatility_history
- Recent data (through Sep 2026)
- Old data (from Feb 2019)

⚠ **Unknown** (need more queries):
- Percentage of zero bids
- Coverage gaps
- Missing data percentage

---

## Project Feasibility: **YES**

### You CAN:
1. ✓ Compare option-implied volatility (iv_current) vs realized (hv_current)
2. ✓ Analyze volatility smile (strike vs IV)
3. ✓ Test "traders pay for downside protection" (have call_put, vol, strike)
4. ✓ Get ~7 years of data (Feb 2019 - Sep 2026)
5. ✓ Use for ML classification ("will realized < implied?")

### Limitations:
- API has 30-second timeout for large aggregations
- Need to query in smaller chunks or use sampling
- `hv_current` appears to be **trailing** (past) volatility, not forward
  - For "expected vs actual" comparison, you'll need to:
    - Take `iv_current` at date t
    - Compute forward realized vol from t to t+30 days using yfinance or by looking at hv_current ~30 days later

---

## Recommended Next Steps for Full Project:

1. **Verify hv_current window**: Check if it's 20-day, 30-day, or other trailing period
2. **Build forward comparison**:
   - Query iv_current for your tickers
   - For each date t, compute realized vol over next 30 days
   - Compare distributions
3. **Sample for ML**:
   - Extract (date, ticker, IV, forward_realized_vol, smile_features)
   - Create binary target: realized < IV
   - Check class balance
4. **Volatility smile features**:
   - Query option_chain for each snapshot
   - Compute put/call skew, ATM vol, OTM put premium
5. **Handle API limits**:
   - Cache all queries
   - Query by ticker and month to avoid timeouts
   - Or download the full database locally if Dolt CLI is available

---

## Numbers for Your Proposal Slides:

| Metric | Current Slide | Actual |
|--------|--------------|---------|
| Date range | Feb 2019 - Sep 30, 2026 | ✓ CONFIRMED |
| Example (AAPL 9/30/26) | 26.6% vs 22.4% | ✓ CONFIRMED (26.64% vs 22.37%) |
| Snapshot frequency | ~3 per week | Appears DAILY (need verification) |
| Total rows | 1M+ | Could not verify (API timeout) |
| Expirations per snapshot | 3 | Could not verify |
| Rows per snapshot | ~150 | Could not verify |

---

## Bottom Line:
**The DoltHub options database works for your project!** The key data (IV, HV, option chains, strikes) is all there. Your slide example numbers are accurate. You just need to handle the API timeouts with smarter queries or local downloads.
