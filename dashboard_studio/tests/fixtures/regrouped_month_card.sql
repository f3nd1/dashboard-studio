SELECT
  `__mb_source`.`Year` AS `Year`,
  `__mb_source`.`Month Label` AS `Month Label`,
  `__mb_source`.`Month No` AS `Month No`,
  AVG(
    `__mb_source`.`custom_aggregated_performance_index_api`
  ) AS `avg`
FROM
  (
    SELECT
      CAST(
        `tabQuality Action`.`custom_aggregated_performance_index_api` AS double
      ) AS `custom_aggregated_performance_index_api`,
      CONCAT(
        '',
        YEAR(`tabQuality Action`.`custom_proposed_date`)
      ) AS `Year`,
      CASE
        WHEN YEAR(`tabQuality Action`.`custom_proposed_date`) = 1 THEN '01-Jan'
        WHEN YEAR(`tabQuality Action`.`custom_proposed_date`) = 2 THEN '02-Feb'
        WHEN YEAR(`tabQuality Action`.`custom_proposed_date`) = 3 THEN '03-Mar'
        WHEN YEAR(`tabQuality Action`.`custom_proposed_date`) = 4 THEN '04-Apr'
        WHEN YEAR(`tabQuality Action`.`custom_proposed_date`) = 5 THEN '05-May'
        WHEN YEAR(`tabQuality Action`.`custom_proposed_date`) = 6 THEN '06-Jun'
        WHEN YEAR(`tabQuality Action`.`custom_proposed_date`) = 7 THEN '07-Jul'
        WHEN YEAR(`tabQuality Action`.`custom_proposed_date`) = 8 THEN '08-Aug'
        WHEN YEAR(`tabQuality Action`.`custom_proposed_date`) = 9 THEN '09-Sep'
        WHEN YEAR(`tabQuality Action`.`custom_proposed_date`) = 10 THEN '10-Oct'
        WHEN YEAR(`tabQuality Action`.`custom_proposed_date`) = 11 THEN '11-Nov'
        WHEN YEAR(`tabQuality Action`.`custom_proposed_date`) = 12 THEN '12-Dec'
      END AS `Month Label`,
      YEAR(`tabQuality Action`.`custom_proposed_date`) AS `Month No`
    FROM
      `tabQuality Action`
  ) AS `__mb_source`
GROUP BY
  `__mb_source`.`Year`,
  `__mb_source`.`Month Label`,
  `__mb_source`.`Month No`
ORDER BY
  `__mb_source`.`Month No` ASC,
  `__mb_source`.`Year` ASC,
  `__mb_source`.`Month Label` ASC
