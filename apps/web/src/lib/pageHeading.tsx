import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

/**
 * What the top bar says, set by whichever page is open.
 *
 * The model screens are map screens: the map is the thing being read, and a
 * full page header above it — title, description, status row — cost about a
 * fifth of the viewport to repeat what the sidebar and the input panel already
 * said. Those pages drop the header entirely and put their one useful line
 * here instead, in the bar that was already on screen.
 *
 * Pages that are not map screens leave this alone and keep their own header;
 * the bar then shows the portal-wide line it always did.
 */
export type PageHeading = {
  /** e.g. "CCM — Cyclone Classifier Model (IWFM / BUET)" */
  title: string;
  /** RFP module number, rendered as a quiet tag after the title. */
  module?: string;
};

const DEFAULT_LINE =
  "Anticipatory action for Bangladesh · data shown in Asia/Dhaka (+06)";

type HeadingContext = {
  heading: PageHeading | null;
  setHeading: (heading: PageHeading | null) => void;
};

const Context = createContext<HeadingContext | null>(null);

export function PageHeadingProvider({ children }: { children: ReactNode }) {
  const [heading, setHeading] = useState<PageHeading | null>(null);
  const value = useMemo(() => ({ heading, setHeading }), [heading]);
  return <Context.Provider value={value}>{children}</Context.Provider>;
}

/**
 * Put this page's line in the top bar for as long as the page is mounted.
 *
 * Clears on unmount, so navigating away restores the portal-wide line rather
 * than leaving the last model's name over an unrelated screen.
 */
export function usePageHeading(title: string, module?: string): void {
  const context = useContext(Context);
  const setHeading = context?.setHeading;

  useEffect(() => {
    if (!setHeading) return;
    setHeading({ title, module });
    return () => setHeading(null);
  }, [setHeading, title, module]);
}

/** The line the top bar should render right now. */
export function useTopBarHeading(): PageHeading | null {
  return useContext(Context)?.heading ?? null;
}

export { DEFAULT_LINE as DEFAULT_TOP_BAR_LINE };
