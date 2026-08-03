SELECT
  `__mb_source`.`TabQuality Performance Outcomes Performance Childta_d700d9c7` AS `TabQuality Performance Outcomes Performance Childta_d700d9c7`,
  `__mb_source`.`avg` AS `avg`
FROM
  (
    SELECT
      `TabQuality Performance Outcomes Performance Childta_70767e69`.`year` AS `TabQuality Performance Outcomes Performance Childta_d700d9c7`,
      AVG(`TabQuality Performance Outcomes Performance Childta_70767e69`.`value`) AS `avg`
    FROM
      `tabQuality Performance Outcomes`
      LEFT JOIN (
        SELECT
          `tabQuality Performance Outcomes Performance Childtable`.`name` AS `name`,
          `tabQuality Performance Outcomes Performance Childtable`.`parent` AS `parent`,
          `tabQuality Performance Outcomes Performance Childtable`.`year` AS `year`,
          `tabQuality Performance Outcomes Performance Childtable`.`value` AS `value`
        FROM
          `tabQuality Performance Outcomes Performance Childtable`
      ) AS `TabQuality Performance Outcomes Performance Childta_70767e69` ON `tabQuality Performance Outcomes`.`name` = `TabQuality Performance Outcomes Performance Childta_70767e69`.`parent`
    WHERE
      `tabQuality Performance Outcomes`.`name` = 'Student Academic Performance Index (Overall)'
    GROUP BY
      `TabQuality Performance Outcomes Performance Childta_70767e69`.`year`
    ORDER BY
      `TabQuality Performance Outcomes Performance Childta_70767e69`.`year` ASC
  ) AS `__mb_source`
