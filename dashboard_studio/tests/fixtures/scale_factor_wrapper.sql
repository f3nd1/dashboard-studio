SELECT
  CAST(
    AVG(`__mb_source`.`Q1`) + AVG(`__mb_source`.`Q5`) AS double
  ) / 2.0 AS `Actual No`
FROM
  (
    SELECT
      `TabStaff Onboarding Survey - Survey Entry`.`qn_1` * 5 AS `Q1`,
      `TabStaff Onboarding Survey - Survey Entry`.`qn_5` * 5 AS `Q5`
    FROM
      ( select * from `tabSurvey Tracking` ) AS `__mb_source`
      LEFT JOIN (
        SELECT `tabSurvey Tracking List of Surveys Childtable`.`name` AS `name`,
          `tabSurvey Tracking List of Surveys Childtable`.`parent` AS `parent`,
          `tabSurvey Tracking List of Surveys Childtable`.`survey_entry` AS `survey_entry`
        FROM `tabSurvey Tracking List of Surveys Childtable`
      ) AS `TabSurvey Tracking List Of Surveys Childtable - name` ON `__mb_source`.`name` = `TabSurvey Tracking List Of Surveys Childtable - name`.`parent`
      LEFT JOIN (
        SELECT `tabStaff Onboarding Survey`.`name` AS `name`,
          `tabStaff Onboarding Survey`.`qn_1` AS `qn_1`,
          `tabStaff Onboarding Survey`.`qn_5` AS `qn_5`
        FROM `tabStaff Onboarding Survey`
      ) AS `TabStaff Onboarding Survey - Survey Entry` ON `TabSurvey Tracking List Of Surveys Childtable - name`.`survey_entry` = `TabStaff Onboarding Survey - Survey Entry`.`name`
    WHERE
      `__mb_source`.`survey_name` = 'Staff Onboarding Survey'
  ) AS `__mb_source`
