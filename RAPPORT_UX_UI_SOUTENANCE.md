# Rapport de Conception IHM & Expérience Utilisateur (UX/UI)
**Projet : Unified Agent (Inetum)**

Ce document met en lumière l'ensemble des fonctionnalités, des choix ergonomiques et des innovations techniques implémentés dans l'Interface Homme-Machine (IHM) de l'Unified Agent. Il a pour but de fournir des arguments solides pour convaincre un jury de la maturité, du professionnalisme et de la robustesse de l'application.

---

## 1. Philosophie de Design : Une Approche "Premium"
L'objectif premier de l'interface était de rompre avec les prototypes académiques classiques pour offrir une application digne d'un produit SaaS (Software as a Service) prêt pour la production.

* **Design System Moderne (Dark Mode Natif) :** Utilisation d'une charte graphique sombre élégante (fonds profonds `#0f172a`, accents `#6366f1`), inspirée des meilleurs outils du marché (comme ChatGPT ou Claude). Le contraste est optimisé pour réduire la fatigue visuelle.
* **Typographie Professionnelle :** Intégration de la police Google *Inter*, réputée pour son excellente lisibilité sur les interfaces numériques complexes.
* **Micro-Interactions et Fluidité :** Remplacement des fenêtres d'alerte (`alert()`) bloquantes par un **système de Toast Notifications** (animations d'apparition/disparition fluides). L'interface réagit au survol (hover) avec des effets de transition, renforçant la sensation de réactivité.

---

## 2. L'Espace Utilisateur : Fluidité et Productivité
L'interface de conversation a été conçue pour que l'utilisateur puisse gérer son savoir de manière intuitive.

* **Rendu du Texte Enrichi (Markdown) :** Les réponses de l'IA ne sont pas de simples blocs de texte brut. L'interface utilise `marked.js` pour parser le contenu en temps réel, offrant un rendu propre des titres, listes, textes en gras, et surtout une **coloration syntaxique** pour le code source.
* **Gestion Avancée de l'Historique (Sidebar) :**
  * **Épinglage (Pin) :** L'utilisateur peut épingler ses conversations les plus importantes en haut de la liste.
  * **Soft-Delete (Archivage) :** Plutôt qu'une suppression brutale, l'utilisateur a la possibilité d'archiver (corbeille) les conversations, garantissant qu'elles ne polluent plus sa vue principale tout en étant conservées côté serveur.
  * **Eager Loading :** Le chat est immédiatement réactif sans latence au démarrage, améliorant drastiquement l'expérience lors de la première interaction.

---

## 3. Le Dashboard Administrateur : Audit et Contrôle Total (Le point fort 🚀)
Le tableau de bord administrateur a été entièrement repensé pour offrir une vue "Tour de contrôle", garantissant sécurité et traçabilité, des arguments majeurs pour les entreprises (Inetum).

### A. Traçabilité "Zero Perte" et Sécurité des Données
* **Gestion des Onglets (Tabs) :** Séparation claire entre les "Conversations Actives" et les "Archives Supprimées", permettant de ne pas surcharger l'écran tout en gardant l'historique accessible.
* **Mécanique de Double Suppression (Soft & Hard Delete) :**
  * Si un utilisateur clique sur "Supprimer", la donnée disparaît de son interface (mise à jour du flag `is_deleted = 1` en base de données).
  * L'administrateur, lui, **conserve la trace** de cette conversation supprimée dans son onglet dédié, assurant un Audit Trail parfait.
* **Outil de Purge (Bulk Delete) :** Ajout récent de cases à cocher (Checkboxes) permettant à l'administrateur de sélectionner plusieurs archives et de procéder à une suppression physique de la base de données (PostgreSQL), respectant ainsi les contraintes RGPD (droit à l'oubli).

### B. Audit par "Click-to-View" (Modales)
* Au lieu de se contenter de métadonnées (Date, Utilisateur), l'administrateur peut **cliquer sur n'importe quelle transaction** pour ouvrir une fenêtre modale élégante superposée à l'écran. 
* Cette modale reconstitue la conversation sous forme de bulles (bleues pour l'utilisateur, grises pour l'IA), permettant un contrôle qualité instantané des réponses fournies par le RAG.

### C. Gestion Documentaire Intuitive
* **Dropzone Upload :** Une zone de glisser-déposer (Drag & Drop) visuellement attractive pour l'ingestion de nouveaux documents dans le RAG.
* **Tableau de Statut :** Un tableau récapitulatif affiche l'état d'ingestion des fichiers (Réussite, Erreur), synchronisé directement avec la base vectorielle FAISS et BM25.

---

## 4. Arguments Techniques pour le Jury
* **Découplage Front/Back :** L'interface a été construite en HTML/CSS/JS "Vanilla" hautement optimisé, interrogeant des APIs REST Flask. Cela prouve une architecture propre, sans surcharge de frameworks complexes, ce qui allège l'application et la rend ultra-rapide.
* **Fiabilité (PostgreSQL) :** Toute la donnée manipulée par l'interface (documents, sessions, états de suppression) n'est plus stockée de manière volatile (client-side), mais bel et bien sécurisée dans une base de données relationnelle robuste de grade production.

## 💡 Conclusion pour le pitch oral
> *"L'interface de l'Unified Agent n'est pas seulement une vitrine technologique ; c'est un produit pensé pour les utilisateurs et sécurisé pour les administrateurs. Nous avons prouvé qu'il est possible de concilier une expérience utilisateur (UX) digne des géants de la tech, avec des exigences métiers strictes (Audit, Traçabilité, RGPD) imposées par le contexte d'entreprise."*
