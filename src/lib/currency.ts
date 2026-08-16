export type Currency = "GBP" | "USD";

/** Canonical prices in the database are stored in GBP (sterling). */
export const GBP_TO_USD = 1.27;

export const CURRENCY_META: Record<
  Currency,
  { code: Currency; symbol: string; locale: string; label: string }
> = {
  GBP: { code: "GBP", symbol: "£", locale: "en-GB", label: "GBP (£)" },
  USD: { code: "USD", symbol: "$", locale: "en-US", label: "USD ($)" },
};

export function convertFromGbp(amountGbp: number, currency: Currency): number {
  if (currency === "USD") {
    return Math.round(amountGbp * GBP_TO_USD);
  }
  return amountGbp;
}

export function formatMoney(amountGbp: number, currency: Currency): string {
  const value = convertFromGbp(amountGbp, currency);
  const { locale, code } = CURRENCY_META[currency];
  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency: code,
    maximumFractionDigits: 0,
  }).format(value);
}

export function getBudgetOptions(currency: Currency) {
  return [
    {
      value: "under-5k",
      label: `Under ${formatMoney(5000, currency)}`,
    },
    {
      value: "5k-10k",
      label: `${formatMoney(5000, currency)} — ${formatMoney(10000, currency)}`,
    },
    {
      value: "10k-25k",
      label: `${formatMoney(10000, currency)} — ${formatMoney(25000, currency)}`,
    },
    {
      value: "25k-50k",
      label: `${formatMoney(25000, currency)} — ${formatMoney(50000, currency)}`,
    },
    {
      value: "50k-plus",
      label: `${formatMoney(50000, currency)}+`,
    },
  ];
}
