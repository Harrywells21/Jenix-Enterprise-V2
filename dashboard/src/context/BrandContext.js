import { createContext, useContext, useState, useEffect } from "react";

const BrandContext = createContext(null);

const DEFAULT = {
  company_name:  "JENIX Enterprise",
  logo_text:     "JENIX",
  logo_subtext:  "ENTERPRISE v2.0",
  primary_color: "#00bcd4",
  powered_by:    true,
  favicon_emoji: "🖥",
};

export function BrandProvider({ children }) {
  const [brand, setBrand] = useState(DEFAULT);

  useEffect(() => {
    fetch("http://localhost:8000/whitelabel/public")
      .then(r => r.json())
      .then(d => setBrand({ ...DEFAULT, ...d }))
      .catch(() => {});
  }, []);

  return (
    <BrandContext.Provider value={{ brand, setBrand }}>
      {children}
    </BrandContext.Provider>
  );
}

export const useBrand = () => useContext(BrandContext);
