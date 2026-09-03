ALTER TABLE sector_profiles
  ADD COLUMN IF NOT EXISTS robotrelevant_aandeel_pct DECIMAL(5,2),
  ADD COLUMN IF NOT EXISTS robot_ondersteuning_pct   DECIMAL(5,2),
  ADD COLUMN IF NOT EXISTS robot_augmentatie_pct     DECIMAL(5,2),
  ADD COLUMN IF NOT EXISTS robot_vervanging_pct      DECIMAL(5,2),
  ADD COLUMN IF NOT EXISTS nea_fysiek_belastend_pct  DECIMAL(5,2),
  ADD COLUMN IF NOT EXISTS robot_params_herkomst     JSONB,
  ADD COLUMN IF NOT EXISTS robot_params_peildatum    DATE,
  ADD COLUMN IF NOT EXISTS robot_params_versie       TEXT,
  ADD COLUMN IF NOT EXISTS robot_params_onzekerheid  SMALLINT;

COMMENT ON COLUMN sector_profiles.robotrelevant_aandeel_pct IS
  'Modelmatige bovengrens: aandeel van al het werk in de sector waarvoor fysieke robotica plausibel is. Niet gelijk aan het NEA-aandeel fysiek belastend werk, zie nea_fysiek_belastend_pct.';

COMMENT ON COLUMN sector_profiles.nea_fysiek_belastend_pct IS
  'TNO/CBS NEA 2024, ter vergelijking geregistreerd. Wordt niet als robotrelevante bovengrens gebruikt: in ICT, finance, onderwijs en overheid wordt deze maat mede gedragen door beeldschermwerk en repetitieve bewegingen.';

COMMENT ON COLUMN sector_profiles.robot_ondersteuning_pct IS
  'Mens voert uit, machine draagt de last. Tilhulp, exoskelet, manipulator. Onderling exclusief met augmentatie en vervanging.';

COMMENT ON COLUMN sector_profiles.robot_augmentatie_pct IS
  'Machine en mens delen de taak, de mens beoordeelt. Cobot, semi-autonome inspectie, bediening op afstand.';

COMMENT ON COLUMN sector_profiles.robot_vervanging_pct IS
  'Autonome uitvoering zonder mens in de lus. Nooit gebruiken als prognose van FTE-verlies.';

COMMENT ON COLUMN sector_profiles.robot_params_herkomst IS
  'Per veld: waarde, betrouwbaarheid (hard cijfer, afgeleid of inschatting), toelichting en bronnen met jaar en url. Deze kolom bestaat omdat rag.py gestructureerde cijfers als exacte feiten presenteert — zonder herkomst zou een ModellenWerk-schatting hetzelfde gezag krijgen als een FTE-telling.';

COMMENT ON COLUMN sector_profiles.robot_params_onzekerheid IS
  'Onzekerheidsmarge in procentpunten op de som van de drie robotvelden.';

ALTER TABLE sector_profiles DROP CONSTRAINT IF EXISTS robot_som_onder_robotrelevant;

ALTER TABLE sector_profiles ADD CONSTRAINT robot_som_onder_robotrelevant CHECK (
  COALESCE(robot_ondersteuning_pct, 0)
+ COALESCE(robot_augmentatie_pct, 0)
+ COALESCE(robot_vervanging_pct, 0)
<= COALESCE(robotrelevant_aandeel_pct, 100)
);

ALTER TABLE sector_profiles DROP CONSTRAINT IF EXISTS robot_pct_bereik;

ALTER TABLE sector_profiles ADD CONSTRAINT robot_pct_bereik CHECK (
  COALESCE(robotrelevant_aandeel_pct, 0) BETWEEN 0 AND 100
  AND COALESCE(robot_ondersteuning_pct, 0) BETWEEN 0 AND 100
  AND COALESCE(robot_augmentatie_pct, 0) BETWEEN 0 AND 100
  AND COALESCE(robot_vervanging_pct, 0) BETWEEN 0 AND 100
);

UPDATE documents SET sector = 'finance' WHERE sector IN ('financieel', 'financiele_dienstverlening');

UPDATE documents SET sector = 'industrie' WHERE sector = 'automotive';

UPDATE documents SET sector = replace(sector, 'financiele_dienstverlening', 'finance') WHERE sector LIKE '%financiele_dienstverlening%';

UPDATE documents SET sector = replace(sector, 'financieel', 'finance') WHERE sector LIKE '%financieel%' AND sector NOT LIKE '%finance%';

UPDATE documents SET sector = replace(sector, 'automotive', 'industrie') WHERE sector LIKE '%automotive%' AND sector NOT LIKE '%industrie%';

UPDATE documents SET sector = replace(sector, 'automotive,', '') WHERE sector LIKE '%automotive%';

UPDATE documents SET sector = replace(sector, ',automotive', '') WHERE sector LIKE '%automotive%';
