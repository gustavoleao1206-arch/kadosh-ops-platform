"""Dados de demonstração para desenvolvimento. Nunca roda em produção (ver cli.py).

Fase 1: usuários, catálogo (tabela de preços 2026 da Kadosh), clientes e veículos.
As fases seguintes acrescentam OS, pagamentos e agenda.
"""

from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models import Client, Service, User, Vehicle, WorkOrder, WorkOrderEvent, WorkOrderItem

DEMO_ADMIN = ("Gustavo (admin)", "admin@kadosh.com.br", "admin12345!")
DEMO_STAFF = ("Sócio (staff)", "socio@kadosh.com.br", "socio12345!")

SERVICOS = [
    # nome, descrição, valor_centavos, duração_min
    ("Lavagem Simples — Hatch/Sedan", "Lavagem externa completa e limpeza básica interna.", 12990, 60),
    ("Lavagem Simples — SUV/Pickup médio porte", "Lavagem externa completa e limpeza básica interna.", 19990, 75),
    ("Lavagem Simples — Pickup grande porte", "Lavagem externa completa e limpeza básica interna.", 24990, 90),
    ("Lavagem Premium — Hatch/Sedan", "Lavagem externa detalhada, limpeza interna, caixas de roda e proteção de pintura.", 39990, 120),
    ("Lavagem Premium — SUV/Pickup médio porte", "Lavagem externa detalhada, limpeza interna, caixas de roda e proteção de pintura.", 49990, 150),
    ("Lavagem Premium — Pickup grande porte", "Lavagem externa detalhada, limpeza interna, caixas de roda e proteção de pintura.", 54990, 180),
    ("Lavagem de Motor", "Limpeza técnica do cofre do motor, com proteção dos componentes sensíveis. Sob avaliação.", 21990, 60),
    ("Lavagem de Chassi", "Lavagem completa da parte inferior do veículo. Sob avaliação.", 49990, 120),
    ("Remoção de Chuva Ácida", "Eliminação de manchas de contaminação química sobre pintura e vidros.", 24990, 90),
    ("Higienização Interna Completa", "Desmontagem de assoalhos e bancos para higienização profunda.", 79990, 360),
    ("Polimento Técnico", "Correção da pintura em etapas — riscos, hologramas e marcas de lavagem.", 99990, 480),
    ("Vitrificação — Hatch/Sedan", "Proteção cerâmica de alta durabilidade.", 149990, 600),
    ("Vitrificação — SUV/Caminhonete", "Proteção cerâmica de alta durabilidade.", 199990, 720),
]

CLIENTES = [
    ("Ruan Oliveira", "5582999110001", None, [("BRA2E19", "Honda", "Civic EX", "Prata", 2001)]),
    ("Maria Souza", "5582999110002", "maria@example.com", [("ABC1D23", "Toyota", "Corolla XEi", "Branco", 2020)]),
    ("João Silva", "5582999110003", None, [("BMW2X34", "BMW", "X3", "Preto", 2019), ("KLM4567", "Fiat", "Toro", "Vermelho", 2022)]),
    ("Carla Menezes", "5582999110004", "carla@example.com", [("NEW0A01", "Jeep", "Compass", "Cinza", 2024)]),
    ("Pedro Albuquerque", "5582999110005", None, [(None, "Porsche", "911 GT3", "Cinza", 2025), ("PAB1C23", "Hilux", "SRX", "Branco", 2021)]),
]


def seed_demo() -> None:
    settings = get_settings()
    if settings.is_production:
        raise RuntimeError("Seed de demonstração não roda em produção.")

    with SessionLocal() as db:
        for nome, email, senha in (DEMO_ADMIN, DEMO_STAFF):
            if not db.scalar(select(User.id).where(User.email == email)):
                db.add(
                    User(
                        nome=nome,
                        email=email,
                        password_hash=hash_password(senha),
                        role="admin" if email.startswith("admin") else "staff",
                    )
                )

        for nome, desc, valor, dur in SERVICOS:
            if not db.scalar(select(Service.id).where(Service.nome == nome)):
                db.add(Service(nome=nome, descricao=desc, valor_base_centavos=valor, duracao_estimada_min=dur))

        for nome, fone, email, veiculos in CLIENTES:
            client = db.scalar(select(Client).where(Client.telefone == fone))
            if not client:
                client = Client(nome=nome, telefone=fone, email=email)
                db.add(client)
                db.flush()
            for placa, marca, modelo, cor, ano in veiculos:
                exists = db.scalar(
                    select(Vehicle.id).where(Vehicle.client_id == client.id, Vehicle.modelo == modelo)
                )
                if not exists:
                    db.add(Vehicle(client_id=client.id, placa=placa, marca=marca, modelo=modelo, cor=cor, ano=ano))
        db.commit()

        _agenda_demo(db)
        db.commit()

    print("Seed de demonstração aplicado.")
    print(f"  admin: {DEMO_ADMIN[1]} / {DEMO_ADMIN[2]}")
    print(f"  staff: {DEMO_STAFF[1]} / {DEMO_STAFF[2]}")


def _agenda_demo(db) -> None:
    """Agendamentos de hoje e amanhã + um orçamento aberto, para as telas nascerem com conteúdo."""
    from datetime import timedelta

    from app.services.periods import day_bounds, today_local

    if db.scalar(select(WorkOrder.id)):
        return  # já tem OS: não duplica

    hoje = today_local()
    ini_hoje, _ = day_bounds(hoje)
    ini_amanha, _ = day_bounds(hoje + timedelta(days=1))
    clientes = db.scalars(select(Client).order_by(Client.id)).all()
    servicos = {s.nome: s for s in db.scalars(select(Service)).all()}
    veiculo_de = {c.id: db.scalar(select(Vehicle).where(Vehicle.client_id == c.id).order_by(Vehicle.id)) for c in clientes}

    def nova(cliente, servico_nomes, *, quando=None, status="agendado"):
        veiculo = veiculo_de.get(cliente.id)
        wo = WorkOrder(
            client_id=cliente.id,
            vehicle_id=veiculo.id if (veiculo and status != "orcamento") else None,
            status=status,
            scheduled_at=quando,
            created_by=1,
        )
        db.add(wo)
        db.flush()
        total = 0
        for nome in servico_nomes:
            servico = servicos.get(nome)
            if servico is None:
                continue
            db.add(
                WorkOrderItem(
                    work_order_id=wo.id, service_id=servico.id, descricao=servico.nome,
                    valor_centavos=servico.valor_base_centavos,
                )
            )
            total += servico.valor_base_centavos
        wo.valor_total_centavos = total
        if quando:
            wo.previsao_conclusao = quando + timedelta(minutes=sum(
                servicos[n].duracao_estimada_min for n in servico_nomes if n in servicos
            ))
        db.add(WorkOrderEvent(work_order_id=wo.id, tipo="status", para=status, user_id=1))

    nova(clientes[0], ["Lavagem Premium — Hatch/Sedan"], quando=ini_hoje + timedelta(hours=8))
    nova(clientes[1], ["Higienização Interna Completa"], quando=ini_hoje + timedelta(hours=10, minutes=30), status="confirmado")
    nova(clientes[2], ["Polimento Técnico", "Vitrificação — SUV/Caminhonete"], quando=ini_amanha + timedelta(hours=9))
    nova(clientes[3], ["Vitrificação — Hatch/Sedans"] if "Vitrificação — Hatch/Sedans" in servicos else ["Vitrificação — Hatch/Sedan"], status="orcamento")


if __name__ == "__main__":
    seed_demo()
