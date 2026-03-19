class Foundrygate < Formula
  desc "Local OpenAI-compatible AI gateway for OpenClaw and other AI-native clients"
  homepage "https://github.com/typelicious/FoundryGate"
  url "https://github.com/typelicious/FoundryGate/archive/refs/tags/v1.3.0.tar.gz"
  sha256 "98bdd7f6cd6a5dd5a9e3723edeeac530cce41b3288d62c4b847726f16b3c7f86"
  license "Apache-2.0"
  head "https://github.com/typelicious/FoundryGate.git", branch: "main"

  depends_on "rust" => :build
  depends_on "python@3.12"

  def install
    python = Formula["python@3.12"].opt_bin/"python3.12"

    # Build native Python extensions from source with extra Mach-O header
    # space so Homebrew's linkage fixups do not trip over vendored wheels.
    ENV["PIP_NO_BINARY"] = "pydantic-core,watchfiles"
    ENV.append "RUSTFLAGS", " -C link-arg=-Wl,-headerpad_max_install_names"
    ENV.append "LDFLAGS", " -Wl,-headerpad_max_install_names"

    system python, "-m", "venv", libexec
    system libexec/"bin/pip", "install", "--upgrade", "pip", "setuptools", "wheel"
    system libexec/"bin/pip", "install", buildpath

    pkgshare.install buildpath.children

    (bin/"foundrygate").write <<~SH
      #!/bin/bash
      set -euo pipefail
      mkdir -p "#{etc}/foundrygate" "#{var}/lib/foundrygate"
      export FOUNDRYGATE_CONFIG_FILE="${FOUNDRYGATE_CONFIG_FILE:-#{etc}/foundrygate/config.yaml}"
      export FOUNDRYGATE_DB_PATH="${FOUNDRYGATE_DB_PATH:-#{var}/lib/foundrygate/foundrygate.db}"
      cd "#{etc}/foundrygate"
      exec "#{libexec}/bin/python" -m foundrygate "$@"
    SH

    (bin/"foundrygate-stats").write <<~SH
      #!/bin/bash
      set -euo pipefail
      export FOUNDRYGATE_CONFIG_FILE="${FOUNDRYGATE_CONFIG_FILE:-#{etc}/foundrygate/config.yaml}"
      export FOUNDRYGATE_DB_PATH="${FOUNDRYGATE_DB_PATH:-#{var}/lib/foundrygate/foundrygate.db}"
      cd "#{etc}/foundrygate"
      exec "#{libexec}/bin/foundrygate-stats" "$@"
    SH

    %w[
      foundrygate-doctor
      foundrygate-health
      foundrygate-onboarding-report
      foundrygate-onboarding-validate
      foundrygate-update-check
    ].each do |helper|
      (bin/helper).write <<~SH
        #!/bin/bash
        set -euo pipefail
        mkdir -p "#{etc}/foundrygate" "#{var}/lib/foundrygate"
        export FOUNDRYGATE_CONFIG_FILE="${FOUNDRYGATE_CONFIG_FILE:-#{etc}/foundrygate/config.yaml}"
        export FOUNDRYGATE_ENV_FILE="${FOUNDRYGATE_ENV_FILE:-#{etc}/foundrygate/foundrygate.env}"
        export FOUNDRYGATE_DB_PATH="${FOUNDRYGATE_DB_PATH:-#{var}/lib/foundrygate/foundrygate.db}"
        export FOUNDRYGATE_PYTHON="#{libexec}/bin/python"
        exec "#{pkgshare}/scripts/#{helper}" "$@"
      SH
    end
  end

  def post_install
    (etc/"foundrygate").mkpath
    (var/"lib/foundrygate").mkpath
    (var/"log/foundrygate").mkpath

    config_path = etc/"foundrygate/config.yaml"
    env_path = etc/"foundrygate/foundrygate.env"

    config_path.write((pkgshare/"config.yaml").read) unless config_path.exist?
    env_path.write((pkgshare/".env.example").read) unless env_path.exist?
  end

  service do
    run [opt_bin/"foundrygate"]
    working_dir etc/"foundrygate"
    environment_variables(
      FOUNDRYGATE_CONFIG_FILE: etc/"foundrygate/config.yaml",
      FOUNDRYGATE_DB_PATH: var/"lib/foundrygate/foundrygate.db",
    )
    keep_alive true
    log_path var/"log/foundrygate/output.log"
    error_log_path var/"log/foundrygate/error.log"
  end

  test do
    assert_match "foundrygate #{version}", shell_output("#{bin}/foundrygate --version")
  end
end
