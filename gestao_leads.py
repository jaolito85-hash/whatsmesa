import csv
import os

def check_leads():
    csv_path = 'LEADS_50_KLINK.csv'
    if not os.path.exists(csv_path):
        print("Arquivo de leads nao encontrado.")
        return

    print("\n" + "="*60)
    print("      GERENCIADOR DE PROSPECCAO KLINK - TOP LEADS")
    print("="*60)
    
    with open(csv_path, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            if i >= 15: break # Mostrar os top 15 no resumo rápido
            print(f"[{i+1}] {row['Nome'].ljust(25)} | {row['Cidade'].ljust(15)} | WhatsApp: {row['WhatsApp']}")
    
    print("="*60)
    print(f"Total de 50 leads prontos no arquivo {csv_path}")
    print("Dica: Use os scripts em SCRIPTS_ABORDAGEM.md para iniciar as vendas.")
    print("="*60 + "\n")

if __name__ == "__main__":
    check_leads()
