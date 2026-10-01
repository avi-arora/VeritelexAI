"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button, input } from "./ui";

const OTP = ["3", "9", "1", "7", "2", ""];

export function LoginScreen() {
  const router = useRouter();
  const [step, setStep] = useState<"creds" | "otp">("creds");

  return (
    <div className="grid min-h-[calc(100vh-34px)] grid-cols-2 max-md:grid-cols-1">
      <div className="flex flex-col justify-between gap-10 bg-navy px-14 pt-14 pb-12 max-md:px-8">
        <div className="flex items-center gap-3">
          <span className="flex size-[34px] items-center justify-center rounded-[7px] bg-[#7fa5c4] font-serif text-base font-semibold text-navy">V</span>
          <span className="text-lg font-semibold tracking-[.02em] text-[#f4f3f0]">VeriteLex AI</span>
        </div>
        <div className="max-w-[440px]">
          <h1 className="mb-[18px] font-serif text-[34px] leading-[1.2] font-semibold text-[#f4f3f0]">The case file, organised for the bench.</h1>
          <p className="m-0 text-base leading-[1.65] text-[#a9bfd1]">
            Upload the documents. VeriteLex builds the chronology, maps it to decided cases, sets out the issues and both parties&apos; positions — every
            line cited to its source.
          </p>
        </div>
        <span className="text-xs leading-[1.6] text-[#6f8ba3]">DIFC Courts · UAE data residency · every session audited</span>
      </div>

      <div className="flex items-center justify-center bg-white p-12 max-md:px-6">
        {step === "creds" ? (
          <form
            className="flex w-full max-w-[380px] flex-col gap-5"
            onSubmit={(e) => {
              e.preventDefault();
              setStep("otp");
            }}
          >
            <div>
              <h2 className="mb-2 font-serif text-[26px] font-semibold">Sign in</h2>
              <p className="m-0 text-sm leading-[1.6] text-muted-2">Use your DIFC Courts judicial credentials.</p>
            </div>
            <label className="flex flex-col gap-2">
              <span className="text-[13px] font-medium text-body-2">Judicial ID</span>
              <input defaultValue="AF-CFI-0114" autoComplete="username" className={input} />
            </label>
            <label className="flex flex-col gap-2">
              <span className="text-[13px] font-medium text-body-2">Password</span>
              <input type="password" defaultValue="password123" autoComplete="current-password" className={input} />
            </label>
            <Button type="submit" className="h-12 text-sm">Continue</Button>
            <Button variant="outline" className="h-[46px] text-sm" onClick={() => setStep("otp")}>
              Sign in with UAE Pass
            </Button>
          </form>
        ) : (
          <div className="flex w-full max-w-[380px] flex-col gap-5">
            <div>
              <h2 className="mb-2 font-serif text-[26px] font-semibold">Enter your code</h2>
              <p className="m-0 text-sm leading-[1.6] text-muted-2">We sent a 6-digit code to your chambers authenticator.</p>
            </div>
            <div className="grid grid-cols-6 gap-2">
              {OTP.map((v, i) => (
                <div
                  key={i}
                  className="flex h-14 items-center justify-center rounded-lg border font-mono text-[22px] font-medium"
                  style={{ borderColor: v ? "#245C86" : "#d6d2cc" }}
                >
                  {v}
                </div>
              ))}
            </div>
            <Button className="h-12 text-sm" onClick={() => router.push("/cases")}>Verify and continue</Button>
            <button type="button" onClick={() => setStep("creds")} className="self-start p-0 text-[13px] font-medium text-blue">
              Back
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
