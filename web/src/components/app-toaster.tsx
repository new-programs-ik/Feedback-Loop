"use client";

import * as React from "react";
import { Toaster } from "sonner";

/** Sonner follows our `.dark` class (not only the OS setting), so a toast never shows up
 *  light-on-light after the user flips the toggle. */
export function AppToaster() {
  const [theme, setTheme] = React.useState<"light" | "dark">("light");
  React.useEffect(() => {
    const read = () => setTheme(document.documentElement.classList.contains("dark") ? "dark" : "light");
    read();
    const obs = new MutationObserver(read);
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    window.addEventListener("theme-change", read);
    return () => {
      obs.disconnect();
      window.removeEventListener("theme-change", read);
    };
  }, []);
  return (
    <Toaster
      theme={theme}
      position="bottom-right"
      closeButton
      richColors
      toastOptions={{
        classNames: {
          toast: "!rounded-xl !border !shadow-pop !font-sans",
          title: "!text-[13.5px] !font-semibold",
          description: "!text-[12.5px]",
        },
      }}
    />
  );
}
