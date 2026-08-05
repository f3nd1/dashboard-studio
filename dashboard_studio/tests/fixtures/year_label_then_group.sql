SELECT
  `__mb_source`.`Year` AS `Year`,
  AVG(`__mb_source`.`custom_aggregated_performance_index_api`) AS `avg`
FROM
  (
    SELECT
      CAST(`tabQuality Action`.`custom_aggregated_performance_index_api` AS double) AS `custom_aggregated_performance_index_api`,
      CONCAT('', YEAR(`tabQuality Action`.`custom_proposed_date`)) AS `Year`
    FROM
      `tabQuality Action`
  ) AS `__mb_source`
GROUP BY `__mb_source`.`Year`
ORDER BY `__mb_source`.`Year` ASC
