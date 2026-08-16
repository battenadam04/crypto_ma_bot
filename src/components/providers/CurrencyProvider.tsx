"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  type Currency,
  CURRENCY_META,
  formatMoney,
  getBudgetOptions,
} from "@/lib/currency";

const STORAGE_KEY = "portfolio-currency";

type CurrencyContextValue = {
  currency: Currency;
  setCurrency: (currency: Currency) => void;
  toggleCurrency: () => void;
  format: (amountGbp: number) => string;
  budgetOptions: { value: string; label: string }[];
  meta: (typeof CURRENCY_META)[Currency];
};

const CurrencyContext = createContext<CurrencyContextValue | null>(null);

export function CurrencyProvider({ children }: { children: ReactNode }) {
  const [currency, setCurrencyState] = useState<Currency>("GBP");
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored === "GBP" || stored === "USD") {
      setCurrencyState(stored);
    }
    setReady(true);
  }, []);

  const setCurrency = useCallback((next: Currency) => {
    setCurrencyState(next);
    window.localStorage.setItem(STORAGE_KEY, next);
  }, []);

  const toggleCurrency = useCallback(() => {
    setCurrency(currency === "GBP" ? "USD" : "GBP");
  }, [currency, setCurrency]);

  const value = useMemo<CurrencyContextValue>(
    () => ({
      currency,
      setCurrency,
      toggleCurrency,
      format: (amountGbp: number) => formatMoney(amountGbp, currency),
      budgetOptions: getBudgetOptions(currency),
      meta: CURRENCY_META[currency],
    }),
    [currency, setCurrency, toggleCurrency],
  );

  // Avoid hydration mismatch flashing wrong currency
  if (!ready) {
    return (
      <CurrencyContext.Provider value={value}>{children}</CurrencyContext.Provider>
    );
  }

  return (
    <CurrencyContext.Provider value={value}>{children}</CurrencyContext.Provider>
  );
}

export function useCurrency() {
  const ctx = useContext(CurrencyContext);
  if (!ctx) {
    throw new Error("useCurrency must be used within CurrencyProvider");
  }
  return ctx;
}

export function CurrencyToggle({ className = "" }: { className?: string }) {
  const { currency, setCurrency } = useCurrency();

  return (
    <div
      className={`inline-flex items-center rounded-full border border-surface-200 bg-surface-0 p-1 text-xs font-semibold shadow-sm ${className}`}
      role="group"
      aria-label="Currency"
    >
      <button
        type="button"
        onClick={() => setCurrency("GBP")}
        aria-pressed={currency === "GBP"}
        className={`rounded-full px-3 py-1.5 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 ${
          currency === "GBP"
            ? "bg-brand-600 text-white shadow"
            : "text-surface-600 hover:text-surface-900"
        }`}
      >
        £ GBP
      </button>
      <button
        type="button"
        onClick={() => setCurrency("USD")}
        aria-pressed={currency === "USD"}
        className={`rounded-full px-3 py-1.5 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 ${
          currency === "USD"
            ? "bg-brand-600 text-white shadow"
            : "text-surface-600 hover:text-surface-900"
        }`}
      >
        $ USD
      </button>
    </div>
  );
}
