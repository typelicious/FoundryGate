class Faigate < Formula
  desc "Local OpenAI-compatible AI gateway for OpenClaw and other AI-native clients"
  homepage "https://github.com/fusionAIze/faigate"
  url "https://github.com/fusionAIze/faigate/archive/refs/tags/v1.6.2.tar.gz"
  sha256 "ce4e0ddc5dfd6a574496530e2bcdadbce4dc110c985ea00d9699da37fe98bc36"
  license "Apache-2.0"
  head "https://github.com/fusionAIze/faigate.git", branch: "main"

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

    (bin/"faigate").write <<~SH
      #!/bin/bash
      set -euo pipefail
      mkdir -p "#{etc}/faigate" "#{var}/lib/faigate"
      export FAIGATE_CONFIG_FILE="${FAIGATE_CONFIG_FILE:-#{etc}/faigate/config.yaml}"
      export FAIGATE_DB_PATH="${FAIGATE_DB_PATH:-#{var}/lib/faigate/faigate.db}"
      cd "#{etc}/faigate"
      exec "#{libexec}/bin/python" -m faigate "$@"
    SH

    (bin/"faigate-stats").write <<~SH
      #!/bin/bash
      set -euo pipefail
      export FAIGATE_CONFIG_FILE="${FAIGATE_CONFIG_FILE:-#{etc}/faigate/config.yaml}"
      export FAIGATE_DB_PATH="${FAIGATE_DB_PATH:-#{var}/lib/faigate/faigate.db}"
      cd "#{etc}/faigate"
      exec "#{libexec}/bin/faigate-stats" "$@"
    SH

    %w[
      faigate-menu
      faigate-dashboard
      faigate-api-keys
      faigate-auto-update
      faigate-provider-probe
      faigate-provider-setup
      faigate-config-overview
      faigate-config-wizard
      faigate-client-integrations
      faigate-client-scenarios
      faigate-logs
      faigate-restart
      faigate-routing-settings
      faigate-server-settings
      faigate-start
      faigate-status
      faigate-stop
      faigate-doctor
      faigate-health
      faigate-onboarding-report
      faigate-onboarding-validate
      faigate-provider-discovery
      faigate-update
      faigate-update-check
    ].each do |helper|
      (bin/helper).write <<~SH
        #!/bin/bash
        set -euo pipefail
        mkdir -p "#{etc}/faigate" "#{var}/lib/faigate"
        export FAIGATE_CONFIG_FILE="${FAIGATE_CONFIG_FILE:-#{etc}/faigate/config.yaml}"
        export FAIGATE_ENV_FILE="${FAIGATE_ENV_FILE:-#{etc}/faigate/faigate.env}"
        export FAIGATE_DB_PATH="${FAIGATE_DB_PATH:-#{var}/lib/faigate/faigate.db}"
        export FAIGATE_PYTHON="#{libexec}/bin/python"
        exec "#{pkgshare}/scripts/#{helper}" "$@"
      SH
    end
  end

  def post_install
    (etc/"faigate").mkpath
    (var/"lib/faigate").mkpath
    (var/"log/faigate").mkpath

    config_path = etc/"faigate/config.yaml"
    env_path = etc/"faigate/faigate.env"

    config_path.write((pkgshare/"config.yaml").read) unless config_path.exist?
    env_path.write((pkgshare/".env.example").read) unless env_path.exist?
  end

  service do
    run [opt_bin/"faigate"]
    working_dir etc/"faigate"
    environment_variables(
      FAIGATE_CONFIG_FILE: etc/"faigate/config.yaml",
      FAIGATE_DB_PATH: var/"lib/faigate/faigate.db",
    )
    keep_alive true
    log_path var/"log/faigate/output.log"
    error_log_path var/"log/faigate/error.log"
  end

  test do
    assert_match "faigate #{version}", shell_output("#{bin}/faigate --version")
  end
end
