-- Metabase's compiled SQL for UCC's 'Quality Performance Outcomes' report,
-- captured live 2026-08-02. One parent DocType joined to two of its child
-- tables, filtered to one parent record, AVG of a child value grouped by two
-- child columns. The per-table wrappers are passthroughs; the outer one
-- renames, which is why it needs lifting rather than unwrapping.
--
-- Column lists trimmed to the ones the query uses; everything structural is
-- exactly as Metabase emitted it.
SELECT
  `__mb_source`.`TabQuality Performance Actual Value Parameter Child_a3e4a16b` AS `TabQuality Performance Actual Value Parameter Child_a3e4a16b`,
  `__mb_source`.`TabQuality Performance Actual Value Parameter Child_447e54e7` AS `TabQuality Performance Actual Value Parameter Child_447e54e7`,
  AVG(`__mb_source`.`Observe Value`) AS `avg`
FROM
  (
    SELECT
      `TabQuality Performance Actual Value Parameter Child_3c522490`.`actual_value` * 1 AS `Observe Value`,
      `TabQuality Performance Actual Value Parameter Child_3c522490`.`metric` AS `TabQuality Performance Actual Value Parameter Child_a3e4a16b`,
      `TabQuality Performance Actual Value Parameter Child_3c522490`.`year` AS `TabQuality Performance Actual Value Parameter Child_447e54e7`
    FROM
      `tabQuality Performance Outcomes`
      LEFT JOIN (
        SELECT
          `tabQuality Performance Outcomes Performance Childtable`.`name` AS `name`,
          `tabQuality Performance Outcomes Performance Childtable`.`parent` AS `parent`,
          `tabQuality Performance Outcomes Performance Childtable`.`year` AS `year`,
          `tabQuality Performance Outcomes Performance Childtable`.`trend` AS `trend`
        FROM
          `tabQuality Performance Outcomes Performance Childtable`
      ) AS `TabQuality Performance Outcomes Performance Childta_70767e69` ON `tabQuality Performance Outcomes`.`name` = `TabQuality Performance Outcomes Performance Childta_70767e69`.`parent`
      LEFT JOIN (
        SELECT
          `tabQuality Performance Actual Value Parameter Childtable`.`name` AS `name`,
          `tabQuality Performance Actual Value Parameter Childtable`.`parent` AS `parent`,
          `tabQuality Performance Actual Value Parameter Childtable`.`year` AS `year`,
          `tabQuality Performance Actual Value Parameter Childtable`.`actual_value` AS `actual_value`,
          `tabQuality Performance Actual Value Parameter Childtable`.`metric` AS `metric`
        FROM
          `tabQuality Performance Actual Value Parameter Childtable`
      ) AS `TabQuality Performance Actual Value Parameter Child_3c522490` ON `tabQuality Performance Outcomes`.`name` = `TabQuality Performance Actual Value Parameter Child_3c522490`.`parent`
    WHERE
      `tabQuality Performance Outcomes`.`name` = 'Aggregated Performance Index'
  ) AS `__mb_source`
GROUP BY
  `__mb_source`.`TabQuality Performance Actual Value Parameter Child_a3e4a16b`,
  `__mb_source`.`TabQuality Performance Actual Value Parameter Child_447e54e7`
ORDER BY
  `__mb_source`.`TabQuality Performance Actual Value Parameter Child_a3e4a16b` ASC,
  `__mb_source`.`TabQuality Performance Actual Value Parameter Child_447e54e7` ASC
