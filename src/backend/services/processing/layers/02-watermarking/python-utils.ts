import path from "path";
import { PROJECT_ROOT } from "./path-utils";

function normalizePythonBin(bin: string): string {
  if (bin.includes("/") || bin.includes("\\")) {
    return path.isAbsolute(bin) ? bin : path.resolve(PROJECT_ROOT, bin);
  }
  return bin;
}

export function getPythonExecutable(): string {
  const fromEnv = process.env.PYTHON_BIN;
  if (fromEnv && fromEnv.trim().length > 0) {
    return normalizePythonBin(fromEnv.trim());
  }

  return process.platform === "win32" ? "python" : "python3";
}
