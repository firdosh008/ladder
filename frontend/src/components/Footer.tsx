export default function Footer() {
  return (
    <footer className="relative px-6 md:px-10 pb-10 pt-6">
      <div className="max-w-[1400px] mx-auto">
        <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-10 pt-10 border-t border-hairline">
          <div>
            <div className="flex items-center gap-2 mb-3">
              <svg width="18" height="18" viewBox="0 0 32 32" aria-hidden="true">
                <path
                  d="M8 22 L16 8 L24 22"
                  stroke="#E8442A"
                  strokeWidth="2.4"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  fill="none"
                />
                <line
                  x1="11"
                  y1="17"
                  x2="21"
                  y2="17"
                  stroke="#E8442A"
                  strokeWidth="2.4"
                  strokeLinecap="round"
                />
              </svg>
              <span className="font-display text-[18px] text-bone">Ladder</span>
              <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-mist">
                /OS
              </span>
            </div>
            <p className="font-display italic text-[15px] text-bone/55 max-w-[36ch]">
              A production OS for founder-operators who ship videos between
              shipping product.
            </p>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-12 gap-y-6 text-[13px]">
            <FooterCol title="product">
              <a href="#workflow">The path</a>
              <a href="#mind">Intelligence</a>
              <a href="#stack">Stack</a>
            </FooterCol>
            <FooterCol title="pilot">
              <a href="mailto:pilot@ladder.so">Apply</a>
              <a href="#cta">Seats</a>
              <a href="#tour">Tour</a>
            </FooterCol>
            <FooterCol title="co.">
              <a href="#">Changelog</a>
              <a href="#">Principles</a>
              <a href="#">Security</a>
            </FooterCol>
          </div>
        </div>

        <div className="mt-10 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 font-mono text-[11px] text-bone/40">
          <div className="flex items-center gap-4">
            <span>© Ladder Labs · MMXXVI</span>
            <span className="h-3 w-px bg-hairline hidden sm:inline-block" />
            <span className="uppercase tracking-[0.22em]">
              built in an afternoon, refined all week
            </span>
          </div>
          <span className="uppercase tracking-[0.22em]">
            v0.3.0 · commit 4e1a9c2
          </span>
        </div>
      </div>
    </footer>
  );
}

function FooterCol({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="font-mono uppercase tracking-[0.22em] text-[10px] text-bone/40 mb-3">
        {title}
      </div>
      <div className="flex flex-col gap-2 [&>a]:text-bone/80 [&>a:hover]:text-cinnabar [&>a]:transition-colors [&>a]:duration-500">
        {children}
      </div>
    </div>
  );
}
