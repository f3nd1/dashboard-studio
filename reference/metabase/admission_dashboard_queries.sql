-- Total student applicants
SELECT COUNT(*) AS `count`
FROM `tabStudent Applicant`;

-- Approved / shortlisted applicants
SELECT COUNT(*) AS `count`
FROM `tabStudent Applicant`
WHERE `tabStudent Applicant`.`application_status` = 'Approved';

-- Enrolled / admitted students
SELECT COUNT(*) AS `count`
FROM `tabStudent Applicant`
WHERE `tabStudent Applicant`.`application_status` = 'Admitted';

-- Admission success rate
SELECT
  (
    CAST(
      SUM(
        CASE
          WHEN `tabStudent Applicant`.`application_status` = 'Admitted' THEN 1
          ELSE 0.0
        END
      ) AS double
    ) / NULLIF(CAST(COUNT(*) AS double), 0.0)
  ) * 100 AS `Count`
FROM `tabStudent Applicant`;

-- Student applicants by year
SELECT
  `tabStudent Applicant`.`academic_year` AS `academic_year`,
  COUNT(*) AS `count`
FROM `tabStudent Applicant`
GROUP BY `tabStudent Applicant`.`academic_year`
ORDER BY `tabStudent Applicant`.`academic_year` ASC;

-- Enrolled students by year
SELECT
  `tabStudent Applicant`.`academic_year` AS `academic_year`,
  COUNT(*) AS `count`
FROM `tabStudent Applicant`
WHERE `tabStudent Applicant`.`application_status` = 'Admitted'
GROUP BY `tabStudent Applicant`.`academic_year`
ORDER BY `tabStudent Applicant`.`academic_year` ASC;

-- Applicants by country
SELECT
  `tabStudent Applicant`.`nationality` AS `nationality`,
  COUNT(*) AS `count`
FROM `tabStudent Applicant`
GROUP BY `tabStudent Applicant`.`nationality`
ORDER BY `tabStudent Applicant`.`nationality` ASC;

-- Applicants by programme
SELECT
  `tabStudent Applicant`.`program` AS `program`,
  COUNT(*) AS `count`
FROM `tabStudent Applicant`
GROUP BY `tabStudent Applicant`.`program`
ORDER BY `tabStudent Applicant`.`program`;

-- Students by agent
SELECT
  `tabStudent Applicant`.`agent` AS `agent`,
  COUNT(*) AS `count`
FROM `tabStudent Applicant`
GROUP BY `tabStudent Applicant`.`agent`
ORDER BY `tabStudent Applicant`.`agent` ASC;
