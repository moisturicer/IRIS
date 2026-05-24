import irisLogo from "@/assets/images/iris_logo.png";
import { cn } from "@/lib/utils";

interface AuthBrandPanelProps {
  variant: "login" | "signup";
  className?: string;
}

function SignupBackgroundDecor() {
  return (
    <>
      <div
        className="absolute rounded-full border border-gold/[0.14] pointer-events-none"
        style={{ width: 540, height: 540, top: "6%", right: "-20%" }}
        aria-hidden
      />
      <div
        className="absolute rounded-full border border-gold/[0.11] pointer-events-none"
        style={{ width: 420, height: 420, top: "12%", right: "-12%" }}
        aria-hidden
      />
      <div
        className="absolute rounded-full border border-gold/[0.08] pointer-events-none"
        style={{ width: 300, height: 300, top: "18%", right: "-4%" }}
        aria-hidden
      />
      <div
        className="absolute rounded-full border border-brand/[0.05] pointer-events-none"
        style={{ width: 380, height: 380, bottom: "-10%", left: "-16%" }}
        aria-hidden
      />
    </>
  );
}

function LoginBackgroundDecor() {
  return (
    <>
      <div
        className="absolute rounded-full border border-brand/[0.06] pointer-events-none"
        style={{ width: 420, height: 420, top: "18%", right: "-12%" }}
        aria-hidden
      />
      <div
        className="absolute rounded-full border border-brand/[0.05] pointer-events-none"
        style={{ width: 320, height: 320, top: "22%", right: "-6%" }}
        aria-hidden
      />
      <div
        className="absolute rounded-full bg-white/60 pointer-events-none"
        style={{ width: 280, height: 280, top: -60, right: -40 }}
      />
      <div
        className="absolute rounded-full bg-white/40 pointer-events-none"
        style={{ width: 200, height: 200, bottom: 120, left: -50 }}
      />
      <div
        className="absolute rounded-full bg-white/50 pointer-events-none"
        style={{ width: 140, height: 140, bottom: 280, right: 60 }}
      />
    </>
  );
}

/**
 * Left-panel branding for login/signup — logo + wordmark as one lockup.
 */
export function AuthBrandPanel({ variant, className }: AuthBrandPanelProps) {
  const isSignup = variant === "signup";

  return (
    <div
      className={cn(
        "relative lg:w-1/2 bg-cream flex flex-col justify-between overflow-hidden",
        "px-8 py-10 sm:px-12 lg:px-14 lg:py-12 min-h-[300px] lg:min-h-screen",
        className
      )}
    >
      {isSignup ? <SignupBackgroundDecor /> : <LoginBackgroundDecor />}

      <div className="relative z-10 flex-1 flex flex-col">
        {isSignup ? (
          <div className="flex items-center gap-3">
            <img
              src={irisLogo}
              alt="IRIS logo"
              className="w-10 h-10 sm:w-11 sm:h-11 object-contain shrink-0"
            />
            <span className="text-[28px] sm:text-[32px] font-extrabold text-brand tracking-[0.12em] leading-none">
              IRIS
            </span>
          </div>
        ) : (
          <div className="flex items-center gap-4 sm:gap-5">
            <div
              className="flex-shrink-0 w-[72px] h-[72px] sm:w-[80px] sm:h-[80px] rounded-2xl bg-white border border-brand/10 shadow-[0_4px_20px_rgba(107,15,18,0.08)] flex items-center justify-center p-2.5"
              aria-hidden
            >
              <img
                src={irisLogo}
                alt="IRIS logo"
                className="w-full h-full object-contain"
              />
            </div>
            <div className="min-w-0 border-l border-brand/15 pl-4 sm:pl-5">
              <p className="text-[10px] sm:text-[11px] font-bold tracking-[0.14em] text-gold uppercase leading-snug">
                Cebu Institute of Technology
              </p>
              <p className="text-[10px] sm:text-[11px] font-bold tracking-[0.12em] text-gold/90 uppercase">
                University
              </p>
              <p className="mt-2 text-[32px] sm:text-[36px] font-extrabold text-brand leading-none tracking-[0.2em]">
                IRIS
              </p>
              <p className="mt-1 text-[11px] font-semibold text-gray-600 tracking-wide">
                CIT-U Research Hub
              </p>
            </div>
          </div>
        )}

        {variant === "login" ? (
          <>
            <p className="mt-8 text-[15px] font-medium text-gray-700 max-w-md">
              Intelligent Research &amp; IP System
            </p>
            <p className="mt-2 text-[13px] text-gray-500 leading-relaxed max-w-sm">
              Securely managing the university&apos;s innovation and research assets.
            </p>
          </>
        ) : (
          <>
            <h1 className="mt-10 sm:mt-14 font-serif leading-[1.05]">
              <span className="block text-[40px] sm:text-[48px] font-bold text-gold">The</span>
              <span className="block text-[40px] sm:text-[48px] font-bold text-brand">
                Academic Curator.
              </span>
            </h1>
            <p className="mt-5 text-[14px] sm:text-[15px] text-brand/90 leading-relaxed max-w-md">
              Welcome to the Digital Vault of CIT-U Intellectual Property. A prestigious archive
              for students and researchers to safeguard and manage their academic assets.
            </p>
            <blockquote className="mt-8 pl-5 border-l-[3px] border-gold max-w-md">
              <p className="font-serif italic text-[15px] text-brand leading-relaxed">
                &ldquo;Transforming complex IP data into a high-end editorial experience that feels
                as permanent as a physical archive.&rdquo;
              </p>
            </blockquote>
            <p className="mt-4 text-[10px] font-bold tracking-[0.12em] text-gold uppercase">
              Cebu Institute of Technology – University
            </p>
          </>
        )}
      </div>

      {variant === "login" && (
        <div className="relative z-10 flex gap-12 sm:gap-16 mt-10 lg:mt-0">
          <div>
            <div className="text-[32px] font-bold text-brand leading-none">1,200+</div>
            <div className="mt-1 text-[10px] font-bold tracking-[0.14em] text-brand uppercase">
              Registered Assets
            </div>
          </div>
          <div>
            <div className="text-[32px] font-bold text-brand leading-none">450+</div>
            <div className="mt-1 text-[10px] font-bold tracking-[0.14em] text-brand uppercase">
              Active Patents
            </div>
          </div>
        </div>
      )}

      <p
        className={cn(
          "relative z-10 text-[11px] text-gray-400 mt-8 lg:mt-6",
          isSignup && "text-center"
        )}
      >
        © 2026 Cebu Institute of Technology - University
      </p>
    </div>
  );
}

/** Compact lockup for the form column on small screens. */
export function AuthFormBrandMark() {
  return (
    <div className="lg:hidden flex items-center justify-center gap-3 mb-8 pb-6 border-b border-gray-100">
      <div className="w-12 h-12 rounded-xl bg-cream border border-brand/10 flex items-center justify-center p-1.5 shrink-0">
        <img src={irisLogo} alt="" className="w-full h-full object-contain" />
      </div>
      <div>
        <p className="text-[20px] font-extrabold text-brand tracking-[0.15em] leading-none">IRIS</p>
        <p className="text-[10px] font-semibold text-gold uppercase tracking-wider mt-0.5">
          CIT-U Research Hub
        </p>
      </div>
    </div>
  );
}
