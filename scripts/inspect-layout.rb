include RBA

layout = Layout.new
layout.read($input)
tops = layout.top_cells.map(&:name).sort
raise "expected exactly one top cell '#{$expected}', found #{tops.inspect}" unless tops == [$expected]

cell = layout.cell($expected)
bbox = cell.bbox
raise "top cell is empty" if bbox.empty?
area = bbox.width * layout.dbu * bbox.height * layout.dbu
raise "layout area is not positive" unless area.positive?

File.write($output, "top_cell: #{$expected}\narea_um2: #{area}\ncell_count: #{layout.cells}\n")
