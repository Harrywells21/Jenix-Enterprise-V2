import { createContext, useContext, useState, useEffect,
         useCallback } from "react";

const BrandContext = createContext(null);

const DEFAULT = {
  company_name:   "JENIX Enterprise",
  logo_text:      "JENIX",
  logo_subtext:   "ENTERPRISE v2.0",
  primary_color:  "#00bcd4",
  accent_color:   "#ffb300",
  sidebar_bg:     "#0d0d1a",
  main_bg:        "#0d0d1a",
  card_bg:        "#13131f",
  powered_by:     true,
  support_email:  "",
  support_url:    "",
  dashboard_title:"Fleet Command Center",
  favicon_emoji:  "🖥",
};

export function BrandProvider({ children }) {
  const [brand, setBrandState] = useState(DEFAULT);

  // Load from server on mount
  useEffect(() => {
    fetch("http://localhost:8000/whitelabel/public")
      .then(r => r.json())
      .then(d => setBrandState(prev => ({ ...prev, ...d })))
      .catch(() => {});
  }, []);

  // ✅ Live update — updates state immediately without page refresh
  const setBrand = useCallback((newBrand) => {
    setBrandState(prev => ({ ...prev, ...newBrand }));
    // Update CSS variables for instant visual feedback
    const root = document.documentElement;
    if (newBrand.primary_color)
      root.style.setProperty("--primary", newBrand.primary_color);
    if (newBrand.sidebar_bg)
      root.style.setProperty("--sidebar-bg", newBrand.sidebar_bg);
  }, []);

  return (
    <BrandContext.Provider value={{ brand, setBrand }}>
      {children}
    </BrandContext.Provider>
  );
}

export const useBrand = () => useContext(BrandContext);
