import os

def fusionner_fichiers_specifiques(dossier_source, fichier_destination):
    # Préfixe recherché
    prefixe = "Formation fonctionnelle Chronotime module GT"
    
    # Liste les fichiers commençant par le préfixe ET finissant par .txt
    fichiers = [f for f in os.listdir(dossier_source) 
                if f.startswith(prefixe) and f.endswith('.txt')]
    
    # Trie les fichiers par nom pour garantir l'ordre
    fichiers.sort()
    
    with open(fichier_destination, 'w', encoding='utf-8') as outfile:
        for nom_fichier in fichiers:
            chemin_complet = os.path.join(dossier_source, nom_fichier)
            
            # Évite de lire le fichier de destination s'il est dans le même dossier
            if nom_fichier == os.path.basename(fichier_destination):
                continue
                
            with open(chemin_complet, 'r', encoding='utf-8') as infile:
                outfile.write(f"\n--- DÉBUT DU FICHIER: {nom_fichier} ---\n")
                outfile.write(infile.read())
                outfile.write(f"\n--- FIN DU FICHIER: {nom_fichier} ---\n")
                print(f"Fusionné : {nom_fichier}")

    print(f"\nTerminé ! Tous les fichiers correspondants ont été fusionnés dans : {fichier_destination}")

# --- CONFIGURATION ---
dossier = '../data/transcripts'  # Dossier contenant les fichiers à fusionner
nom_final = 'formation_chrono_complete.txt'

fusionner_fichiers_specifiques(dossier, nom_final)