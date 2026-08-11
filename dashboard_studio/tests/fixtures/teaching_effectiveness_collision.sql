SELECT
  `__mb_source`.`name` AS `name`,
  AVG(`__mb_source`.`Teaching Effectiveness`) AS `Teaching Effectiveness Average`
FROM
  (
    SELECT
      `TabEnd of Course Survey - Survey Entry`.`teaching_question` * 5 AS `Teaching Effectiveness`,
      `__mb_source`.`name` AS `name`
    FROM
      `tabSurvey Tracking` AS `__mb_source`
      LEFT JOIN `tabSurvey Tracking List of Surveys Childtable` AS `TabSurvey Tracking List Of Surveys Childtable - name` ON `__mb_source`.`name` = `TabSurvey Tracking List Of Surveys Childtable - name`.`parent`
      LEFT JOIN `tabEnd of Course Survey` AS `TabEnd of Course Survey - Survey Entry` ON `TabSurvey Tracking List Of Surveys Childtable - name`.`survey_entry` = `TabEnd of Course Survey - Survey Entry`.`name`
    WHERE
      (
        `__mb_source`.`survey_name` = 'End of Course Survey'
      )
  ) AS `__mb_source`
GROUP BY
  `__mb_source`.`name`
ORDER BY
  `__mb_source`.`name` ASC
