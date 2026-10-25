"""Cria configuração local ou recupera segredos de uma configuração anterior indicada."""

import argparse
from pathlib import Path
import secrets

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", default="teste@example.invalid")
    parser.add_argument(
        "--reuse-env",
        type=Path,
        help="Recupera somente segredos ausentes/de exemplo a partir de um .env anterior do mesmo projeto",
    )
    args = parser.parse_args()
    if (
        "\n" in args.email
        or "\r" in args.email
        or not __import__("re").fullmatch(r"[A-Za-z0-9_.+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", args.email)
    ):
        parser.error("Informe um endereço de e-mail válido.")
    env_path = ROOT / ".env"
    if args.reuse_env:
        if not env_path.exists():
            parser.error("Crie o .env local antes de recuperar os segredos de uma configuração anterior.")
        if args.reuse_env.resolve() == env_path.resolve():
            parser.error("A configuração anterior deve ser um arquivo diferente.")
        original = env_path.read_text(encoding="utf-8-sig")
        prior = args.reuse_env.read_text(encoding="utf-8-sig")

        def parse(text):
            return {
                line.split("=", 1)[0].strip(): line.split("=", 1)[1].strip()
                for line in text.splitlines()
                if "=" in line and not line.lstrip().startswith("#")
            }

        current_values = parse(original)
        previous_values = parse(prior)
        if current_values.get("COMPOSE_PROJECT_NAME") != previous_values.get("COMPOSE_PROJECT_NAME"):
            parser.error("Os nomes dos projetos Docker são diferentes; recuperação interrompida.")
        required = {
            "POSTGRES_PASSWORD",
            "N8N_DB_PASSWORD",
            "AUTOMATION_DB_PASSWORD",
            "APP_DB_PASSWORD",
            "N8N_ENCRYPTION_KEY",
        }
        replacements = {}
        for key in required:
            value = current_values.get(key, "").strip().strip("\"'")
            if not value or value == "GERAR_COM_CONFIGURE":
                recovered = previous_values.get(key, "")
                if (
                    not recovered.strip().strip("\"'")
                    or recovered.strip().strip("\"'") == "GERAR_COM_CONFIGURE"
                ):
                    parser.error(f"A configuração anterior também não possui um valor válido para {key}.")
                replacements[key] = recovered
        result = []
        for line in original.splitlines():
            key = line.split("=", 1)[0].strip() if "=" in line and not line.lstrip().startswith("#") else ""
            if key in replacements:
                line = f"{key}={replacements[key]}"
            result.append(line)
        existing = set(current_values)
        result.extend(f"{key}={value}" for key, value in replacements.items() if key not in existing)
        if replacements:
            env_path.write_text("\n".join(result) + "\n", encoding="utf-8", newline="\n")
        print(f"{len(replacements)} segredos recuperados. Os demais valores do .env foram preservados.")
        return
    if env_path.exists():
        print(".env já existe; configuração preservada. Edite-o para alterar valores.")
        return
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    lines = []
    for line in text.splitlines():
        if "=GERAR_COM_CONFIGURE" in line:
            key = line.split("=", 1)[0]
            value = secrets.token_hex(32)
            line = f"{key}={value}"
        elif line.startswith("AUTOMATION_EMAIL="):
            line = f"AUTOMATION_EMAIL={args.email.lower()}"
        lines.append(line)
    # Exclusão mútua simples: falha se outro processo criar o arquivo primeiro.
    with env_path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines) + "\n")
    print("Criado .env com segredos aleatórios. Não compartilhe esse arquivo.")
    print(
        "Painel em modo local, sem login externo e com identidade simulada. Não publique essa configuração na internet."
    )
    print("Envios reais continuam desabilitados. Próximo comando: docker compose up -d --build")


if __name__ == "__main__":
    main()
